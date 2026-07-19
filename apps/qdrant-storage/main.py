import os
import json
import time
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from confluent_kafka import Consumer, KafkaError

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "log_collection")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC = "log-embeddings"

# Initialize Qdrant client
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Ensure collection exists
def init_collection():
    try:
        collections = client.get_collections().collections
        names = [c.name for c in collections]
        if COLLECTION_NAME not in names:
            print(f"Creating collection {COLLECTION_NAME}")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),  # default for MiniLM
            )
        else:
            print(f"Collection {COLLECTION_NAME} already exists.")
    except Exception as e:
        print(f"Error initializing collection: {e}")
        raise

def main():
    print("Qdrant storage service starting...")
    init_collection()

    consumer_conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP,
        'group.id': 'qdrant-storage-group',
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
                data = json.loads(msg.value().decode('utf-8'))
                embedding = data.get('embedding')
                if embedding is None:
                    print("No embedding found, skipping")
                    continue
                # Prepare payload: exclude embedding to save space? Keep all fields.
                payload = {k: v for k, v in data.items() if k != 'embedding'}
                # Use a UUID based on offset+partition+timestamp? Use Kafka offset as ID.
                # We'll create a point ID from hash of key+offset+timestamp for simplicity.
                # Use msg.offset() etc.
                point_id = msg.offset() + msg.partition() * 1000000  # simple
                point = PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
                client.upsert(collection_name=COLLECTION_NAME, points=[point])
                # Optional: log every 100
                if point_id % 100 == 0:
                    print(f"Stored point {point_id}")
            except Exception as e:
                print(f"Error processing message: {e}")
                continue
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == '__main__':
    main()