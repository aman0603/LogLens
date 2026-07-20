import time
from confluent_kafka import Consumer, KafkaError, Producer
from sqlalchemy.orm import sessionmaker

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import kafka_retry as ll_kafka_retry
from loglens import metrics as ll_metrics

from app.database import Base, engine
from app.schemas import LogEntryCreate
from app.crud import create_log_entry

cfg = ll_config.load_config(
    required=["DATABASE_URL"],
    optional={
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "KAFKA_MAX_RETRIES": 3,
    },
    casts={"KAFKA_MAX_RETRIES": int},
)

SERVICE_NAME = "storage-consumer"
logger = ll_logging.get_logger(SERVICE_NAME)

# Database setup
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def process_message(data: dict, db):
    log = LogEntryCreate(**data)
    create_log_entry(db, log)


def consume_loop():
    conf = {
        "bootstrap.servers": cfg.get("KAFKA_BOOTSTRAP_SERVERS"),
        "group.id": "log-consumer-group",
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
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Consumer error: {msg.error()}")
                break
            ll_kafka_retry.with_retry(
                SERVICE_NAME,
                "logs",
                msg.value(),
                lambda d: process_message(d, db),
                producer=producer,
                max_attempts=max_retries,
                base_backoff=1.0,
            )
    finally:
        db.close()
        consumer.close()
        producer.flush()


if __name__ == "__main__":
    ll_metrics.start_sidecar(port=8000, service=SERVICE_NAME)
    time.sleep(10)
    logger.info("Storage consumer starting")
    consume_loop()
