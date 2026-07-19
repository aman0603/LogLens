import os
import json
import time
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from confluent_kafka import Consumer, KafkaError

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "log_collection")
INPUT_TOPIC = "logs"
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Initialize model
print(f"Loading embedding model {MODEL_NAME}...")
model = SentenceTransformer(MODEL_NAME)
print("Model loaded.")

# Initialize Qdrant client
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def init_collection():
    try:
        collections = qdrant.get_collections().collections
        names = [c.name for c in collections]
        if COLLECTION_NAME not in names:
            print(f"Creating collection {COLLECTION_NAME}")
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        else:
            print(f"Collection {COLLECTION_NAME} already exists.")
    except Exception as e:
        print(f"Error ensuring collection: {e}")
        raise

def main():
    print("Embedding service starting...")
    init_collection()

    consumer_conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP,
        'group.id': 'embedding-service-group',
        'auto.offset.reset': 'earliest'
    }
    consumer = Consumer(consumer_conf)
    consumer.subscribe([INPUT_TOPIC])

    print(f"Consuming from topic {INPUT_TOPIC}")
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(f"Consumer error: {msg.error()}")
                    break

            try:
                log_data = json.loads(msg.value().decode('utf-8'))
                text = log_data.get('message', '')
                if not text:
                    # No text to embed, skip
                    continue
                embedding = model.encode(text).tolist()
                # Create point ID: combine offset, partition, timestamp to avoid duplicates
                # Using offset as base, shift by partition*large number
                point_id = msg.offset() + msg.partition() * 1000000
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=log_data  # store entire log as payload
                )
                qdrant.upsert(collection_name=COLLECTION_NAME, points=[point])
                if point_id % 100 == 0:
                    print(f"Stored embedding for offset {msg.offset()}, partition {msg.partition()}")
            except Exception as e:
                print(f"Error processing message: {e}")
                continue
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == '__main__':
    main()
