import json
import time
import random
from faker import Faker
from confluent_kafka import Producer

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import metrics as ll_metrics

cfg = ll_config.load_config(
    optional={"KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "PRODUCE_INTERVAL": 0.5},
    casts={"PRODUCE_INTERVAL": float},
)

SERVICE_NAME = "log-producer"
logger = ll_logging.get_logger(SERVICE_NAME)

fake = Faker()

conf = {"bootstrap.servers": cfg.get("KAFKA_BOOTSTRAP_SERVERS")}
producer = Producer(conf)


def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def generate_log():
    levels = ["INFO", "WARN", "ERROR", "DEBUG"]
    services = ["api-gateway", "auth-service", "payment-service", "user-service", "order-service"]
    level = random.choice(levels)
    service = random.choice(services)
    message = fake.sentence(nb_words=10)
    return {"level": level, "service": service, "message": message}


def produce_loop():
    interval = cfg.get("PRODUCE_INTERVAL")
    while True:
        log = generate_log()
        producer.produce("logs", json.dumps(log).encode("utf-8"), callback=delivery_report)
        producer.poll(0)
        time.sleep(interval)


if __name__ == "__main__":
    ll_metrics.start_sidecar(port=8000, service=SERVICE_NAME)
    try:
        produce_loop()
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()
