import time
from datetime import datetime, timezone
from confluent_kafka import Consumer, KafkaError, Producer
from sqlalchemy.orm import Session

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import kafka_retry as ll_kafka_retry
from loglens import metrics as ll_metrics

from .database import SessionLocal, Base
from . import schemas, crud, detection

cfg = ll_config.load_config(
    required=["DATABASE_URL"],
    optional={
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "INCIDENT_TIME_WINDOW_SECONDS": 300,
        "KAFKA_MAX_RETRIES": 3,
    },
    casts={"INCIDENT_TIME_WINDOW_SECONDS": int, "KAFKA_MAX_RETRIES": int},
)

SERVICE_NAME = "incident-service"
logger = ll_logging.get_logger(SERVICE_NAME)

TIME_WINDOW = cfg.get("INCIDENT_TIME_WINDOW_SECONDS")
ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL"}
_buffers: dict = {}


def _flush_service(service: str, db: Session):
    logs = _buffers.pop(service, [])
    if not logs:
        return
    canonical = [detection.normalize_log(l) for l in logs]
    incident = detection.build_incident_from_logs(canonical)
    if incident["log_count"] == 0:
        return
    created = crud.create_incident(db, schemas.IncidentCreate(**incident))
    logger.info(f"Created incident {created.id} for service {service}")


def process_message(raw: dict, db: Session):
    canonical = detection.normalize_log(raw)
    service = canonical["service"]
    is_error = canonical["level"] in ERROR_LEVELS

    buf = _buffers.setdefault(service, [])

    if buf and not is_error:
        _flush_service(service, db)
        buf = _buffers.setdefault(service, [])

    buf.append(raw)

    if buf:
        first_ts = detection.normalize_log(buf[0]).get("timestamp")
        last_ts = canonical.get("timestamp")
        if isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
            if (last_ts - first_ts).total_seconds() >= TIME_WINDOW:
                _flush_service(service, db)


def consume_loop():
    conf = {
        "bootstrap.servers": cfg.get("KAFKA_BOOTSTRAP_SERVERS"),
        "group.id": "incident-service-group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }
    consumer = Consumer(conf)
    consumer.subscribe(["logs"])

    producer = Producer({"bootstrap.servers": cfg.get("KAFKA_BOOTSTRAP_SERVERS")})

    db = SessionLocal()
    max_retries = cfg.get("KAFKA_MAX_RETRIES")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                now = datetime.now(timezone.utc)
                for service in list(_buffers.keys()):
                    buf = _buffers[service]
                    if buf:
                        first_ts = detection.normalize_log(buf[0]).get("timestamp")
                        if isinstance(first_ts, datetime):
                            if (now - first_ts).total_seconds() >= TIME_WINDOW:
                                _flush_service(service, db)
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Consumer error: {msg.error()}")
                break
            # Retry + DLQ wrapping (poison messages routed to logs.dlq).
            ll_kafka_retry.with_retry(
                SERVICE_NAME,
                "logs",
                msg.value(),
                lambda data: process_message(data, db),
                producer=producer,
                max_attempts=max_retries,
                base_backoff=1.0,
            )
    finally:
        for service in list(_buffers.keys()):
            _flush_service(service, db)
        db.close()
        consumer.close()
        producer.flush()


if __name__ == "__main__":
    ll_metrics.start_sidecar(port=8000, service=SERVICE_NAME)
    Base.metadata.create_all(bind=SessionLocal().bind)
    time.sleep(10)
    logger.info("Incident service starting")
    consume_loop()
