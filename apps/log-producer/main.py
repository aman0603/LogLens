import json
import time
import random
from faker import Faker
from confluent_kafka import Producer

fake = Faker()

conf = {
    'bootstrap.servers': 'kafka:9092'
}
producer = Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')

def generate_log():
    levels = ['INFO', 'WARN', 'ERROR', 'DEBUG']
    services = ['api-gateway', 'auth-service', 'payment-service', 'user-service', 'order-service']
    level = random.choice(levels)
    service = random.choice(services)
    message = fake.sentence(nb_words=10)
    return {
        'level': level,
        'service': service,
        'message': message
    }

def produce_loop():
    while True:
        log = generate_log()
        producer.produce('logs', json.dumps(log).encode('utf-8'), callback=delivery_report)
        producer.poll(0)
        time.sleep(0.5)  # produce 2 logs per second

if __name__ == '__main__':
    try:
        produce_loop()
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()
