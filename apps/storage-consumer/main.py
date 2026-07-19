import os
import json
import time
from confluent_kafka import Consumer, KafkaError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, LogEntry
from app.schemas import LogEntryCreate
from app.crud import create_log_entry

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://loglens:loglens@postgres:5432/loglens")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Base.metadata)
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Kafka consumer config
conf = {
    'bootstrap.servers': 'kafka:9092',
    'group.id': 'log-consumer-group',
    'auto.offset.reset': 'earliest'
}
consumer = Consumer(conf)
consumer.subscribe(['logs'])

def consume_loop():
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    print(msg.error())
                    break
            else:
                try:
                    data = json.loads(msg.value().decode('utf-8'))
                    log = LogEntryCreate(**data)
                    db = next(get_db())
                    create_log_entry(db, log)
                    db.close()
                except Exception as e:
                    print(f"Error processing message: {e}")
    finally:
        consumer.close()

if __name__ == '__main__':
    # Give Kafka and DB time to start
    time.sleep(10)
    consume_loop()