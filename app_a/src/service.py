import json
import logging
import random
import sys
import time
from os import getenv
from shutil import copytree

from app_a.src.app import ChatProducer
from commons.src.s3 import S3Interface

LOGGER = logging.getLogger("docker_logger")
consoleHandler = logging.StreamHandler(sys.stdout)
LOGGER.addHandler(consoleHandler)
LOGGER.setLevel(logging.DEBUG)  # set logger level


def service(arg_value: str):
    s3 = S3Interface(
        getenv("AWS_S3_BUCKET"),
        getenv("AWS_ACCESS_KEY_ID"),
        getenv("AWS_SECRET_ACCESS_KEY"),
    )

    LOGGER.info("-" * 10)
    LOGGER.info("start")

    # ex: dev/XX_DB/2023-10-05T18:35:00+00:00_2023-10-05T18:40:00+00:00
    separator = "/"
    prefix_enviroment = arg_value.split(separator)[0]
    prefix_subdir = separator.join(arg_value.split(separator)[1:-1])
    package_name = arg_value.split(separator)[-1]

    package_input_path = s3.download_package(
        prefix_enviroment=prefix_enviroment,
        prefix_subdir=prefix_subdir,
        package_name=package_name,
        separator=separator,
    )

    output_prefix_subdir = "YY_app/"
    package_output_path = package_input_path.replace(
        prefix_subdir,
        output_prefix_subdir,
    )

    copytree(
        src=package_input_path,
        dst=package_output_path,
    )

    seconds = random.randint(20, 60*3)
    LOGGER.info("working for %s seconds with '%s'", seconds, arg_value)
    time.sleep(seconds)

    s3.upload_package(
        prefix_enviroment=prefix_enviroment,
        prefix_subdir=output_prefix_subdir,
        package_name=package_name,
        separator=separator,
    )

    LOGGER.info("finish")
    LOGGER.info("-" * 10)


if __name__ == "__main__":
    producer = ChatProducer(
        brokers=getenv("KAFKA_BROKER"),
        topic=getenv("PRODUCER_TOPIC"),
    )
    producer.send_message(
        key=getenv("CONSUMER_CLIENT_ID"),
        message={
            "s3_path": sys.argv[1],
            "status": "init",
            "details": "",
        },
    )
    assert len(sys.argv) == 2
    service(sys.argv[1])
    producer.send_message(
        key=getenv("CONSUMER_CLIENT_ID"),
        message={
            "s3_path": sys.argv[1],
            "status": "end",
            "details": "",
        },
    )
    producer.close()
