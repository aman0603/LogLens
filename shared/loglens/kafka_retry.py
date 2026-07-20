"""Kafka retry and dead-letter queue (DLQ) utilities.

Consumers use ``with_retry`` to process a message with bounded retries and
exponential backoff. If all attempts fail, the original message is published to
a ``<topic>.dlq`` topic so no poison record is lost. Outcomes are recorded to
the shared metrics counter.
"""

import time
import json
import logging
from typing import Callable, Optional

from . import metrics

logger = logging.getLogger("kafka_retry")


def dlq_topic(topic: str) -> str:
    return f"{topic}.dlq"


def with_retry(
    service: str,
    topic: str,
    value: bytes,
    process: Callable[[dict], None],
    producer=None,
    max_attempts: int = 3,
    base_backoff: float = 1.0,
    key: Optional[str] = None,
) -> bool:
    """Process a Kafka message with retry/backoff; route to DLQ on exhaustion.

    Args:
        service: service name (for metrics/logging).
        topic: source topic name.
        value: raw message bytes.
        process: callable that parses + handles the decoded message; raises on failure.
        producer: optional confluent_kafka.Producer to publish to the DLQ.
        max_attempts: total attempts before DLQ.
        base_backoff: initial backoff seconds (doubles each attempt).
        key: optional message key for the DLQ publish.
    Returns True if handled (or DLQ'd), False if it could not be decoded.
    """
    try:
        data = json.loads(value.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        metrics.KAFKA_MESSAGES.labels(service=service, topic=topic, outcome="decode_error").inc()
        logger.error("Failed to decode message on %s; routing to DLQ", topic)
        _publish_dlq(producer, service, topic, value, key)
        return False

    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            process(data)
            metrics.KAFKA_MESSAGES.labels(service=service, topic=topic, outcome="success").inc()
            return True
        except Exception as e:  # noqa: BLE001 - we retry on any failure
            last_err = e
            metrics.KAFKA_MESSAGES.labels(service=service, topic=topic, outcome="retry").inc()
            if attempt < max_attempts:
                time.sleep(base_backoff * (2 ** (attempt - 1)))
    # Exhausted: route to DLQ.
    logger.error("Message on %s failed after %d attempts: %s", topic, max_attempts, last_err)
    metrics.KAFKA_MESSAGES.labels(service=service, topic=topic, outcome="dlq").inc()
    _publish_dlq(producer, service, topic, value, key)
    return True


def _publish_dlq(producer, service: str, topic: str, value: bytes, key: Optional[str]):
    if producer is None:
        return
    try:
        producer.produce(dlq_topic(topic), value, key=key)
        producer.poll(0)
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to publish to DLQ %s: %s", dlq_topic(topic), e)
