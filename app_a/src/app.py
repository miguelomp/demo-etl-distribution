import json
import logging
import subprocess
import threading
import time
import uuid
from typing import Callable

from kafka import KafkaConsumer, KafkaProducer


class ChatProducer:
    def __init__(self, brokers, topic):
        self.topic = topic
        self.producer = KafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    def send_message(self, key, message):
        self.producer.send(self.topic, message, key)
        self.producer.flush()

    def close(self):
        self.producer.close()


class ChatConsumer:
    def __init__(self, brokers, topic, whoami, group_id):
        whoami = f"{whoami}_{str(uuid.uuid4())}"
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=brokers,
            client_id=whoami,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m.startswith(b"{") else json.loads('{{"s3_path": "{0}" }}'.format(m.decode("utf-8"))),
            enable_auto_commit=False,
            # auto_offset_reset="earliest",
        )

    def print_messages(self, subprocess_: Callable = None):
        topics = self.consumer.subscription()
        LOGGER.info(topics)
        # python node\app\src\main.py
        for msg in self.consumer:
            
            if msg is None:
                time.sleep(1)
                continue
            LOGGER.info(msg)
            self.consumer.commit()
            self.consumer.unsubscribe()
            # LOGGER.info("%s: %s", msg.value["user"], msg.value["message"])
            if subprocess_:
                # aqui se llama al proceso
                subprocess_(msg.value["s3_path"])
            self.consumer.subscribe(topics)

    def close(self):
        self.consumer.close()


def service(arg_value: str):
    LOGGER.info("-" * 10)
    subprocess.run(
        [
            "python",
            "-m",
            "app_a.src.service",
            arg_value,
        ]
    )
    LOGGER.info("-" * 10)


def consumer_thread(consumer_obj):
    consumer_obj.print_messages(service)


def init(brokers, topic, client_id, group_id):
    consumer = ChatConsumer(brokers, topic, client_id, group_id)
    consumer_t = threading.Thread(target=consumer_thread, args=(consumer,))
    consumer_t.daemon = True
    consumer_t.start()
    LOGGER.info("Connected. Press Ctrl+C to exit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as what_happened:
        LOGGER.info("Exception unexpected raised")
        LOGGER.info(what_happened)
    finally:
        LOGGER.info("\nClosing kafka connection...")
        consumer.close()
        consumer_t.join


if __name__ == "__main__":
    import sys

    assert len(sys.argv) == 5

    _cid = sys.argv[1]
    _gid = sys.argv[2]
    _broker = sys.argv[3]
    _topic = sys.argv[4]

    LOGGER = logging.getLogger("docker_logger")
    consoleHandler = logging.StreamHandler(sys.stdout)
    LOGGER.addHandler(consoleHandler)
    LOGGER.setLevel(logging.DEBUG)  # set logger level

    init([_broker], _topic, _cid, _gid)
