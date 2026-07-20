from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from confluent_kafka import Consumer, KafkaError, Producer

from loglens import config as ll_config
from loglens import logging as ll_logging
from loglens import kafka_retry as ll_kafka_retry
from loglens import metrics as ll_metrics

cfg = ll_config.load_config(
    required=["QDRANT_HOST"],
    optional={
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "QDRANT_PORT": 6333,
        "QDRANT_COLLECTION": "log_collection",
        "INPUT_TOPIC": "logs",
        "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "KAFKA_MAX_RETRIES": 3,
    },
    casts={"QDRANT_PORT": int, "KAFKA_MAX_RETRIES": int},
)

SERVICE_NAME = "embedding-service"
logger = ll_logging.get_logger(SERVICE_NAME)

KAFKA_BOOTSTRAP = cfg.get("KAFKA_BOOTSTRAP_SERVERS")
QDRANT_HOST = cfg.get("QDRANT_HOST")
QDRANT_PORT = cfg.get("QDRANT_PORT")
COLLECTION_NAME = cfg.get("QDRANT_COLLECTION")
INPUT_TOPIC = cfg.get("INPUT_TOPIC")
MODEL_NAME = cfg.get("EMBEDDING_MODEL")

logger.info(f"Loading embedding model {MODEL_NAME}")
model = SentenceTransformer(MODEL_NAME)
logger.info("Model loaded.")

qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def init_collection():
    try:
        names = [c.name for c in qdrant.get_collections().collections]
        if COLLECTION_NAME not in names:
            logger.info(f"Creating collection {COLLECTION_NAME}")
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        else:
            logger.info(f"Collection {COLLECTION_NAME} already exists.")
    except Exception as e:
        logger.error(f"Error ensuring collection: {e}")
        raise


def process_message(data: dict, msg_meta):
    text = data.get("message", "")
    if not text:
        return
    embedding = model.encode(text).tolist()
    point_id = msg_meta["offset"] + msg_meta["partition"] * 1000000
    point = PointStruct(id=point_id, vector=embedding, payload=data)
    qdrant.upsert(collection_name=COLLECTION_NAME, points=[point])
    if point_id % 100 == 0:
        logger.info(f"Stored embedding for offset {msg_meta['offset']}")


def main():
    init_collection()
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "embedding-service-group",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe([INPUT_TOPIC])
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    max_retries = cfg.get("KAFKA_MAX_RETRIES")
    logger.info(f"Consuming from topic {INPUT_TOPIC}")
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
            meta = {"offset": msg.offset(), "partition": msg.partition()}
            ll_kafka_retry.with_retry(
                SERVICE_NAME,
                INPUT_TOPIC,
                msg.value(),
                lambda d: process_message(d, meta),
                producer=producer,
                max_attempts=max_retries,
                base_backoff=1.0,
            )
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        producer.flush()


if __name__ == "__main__":
    ll_metrics.start_sidecar(port=8000, service=SERVICE_NAME)
    main()
