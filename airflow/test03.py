import functools
import json
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
# This is just for setting up connections in the demo - you should use standard
# methods for setting these connections in production
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.amazon.aws.operators.s3 import S3ListOperator
from airflow.providers.apache.kafka.operators.consume import \
    ConsumeFromTopicOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.utils.trigger_rule import TriggerRule

KAFKA_CONN_ID = "t2"
KAFKA_TOPIC = "services-log"
KAFKA_GID = "airflow_dag_02"
S3_CONN_ID = "s3conn"
# TODO bring S3_BUCKET_NAME from docker compose deployed, it is already defined in the .env file
S3_BUCKET_NAME = "data-dump"
S3_PREFIX = "dev/XX_DB/{{ data_interval_start - macros.timedelta(minutes=5) }}_{{ data_interval_end - macros.timedelta(minutes=5) }}"


def load_connections():
    # Connections needed for this example dag to finish
    from airflow.models import Connection, Variable
    from airflow.utils import db

    db.merge_conn(
        Connection(
            conn_id=KAFKA_CONN_ID,
            conn_type="kafka",
            extra=json.dumps(
                {
                    "bootstrap.servers": "redpanda:9092",
                    "group.id": KAFKA_GID,
                    "enable.auto.commit": False,
                    "auto.offset.reset": "beginning",
                }
            ),
        )
    )

    messages_buffer = Variable.get("messages_buffer", list(), deserialize_json=True)
    Variable.set("messages_buffer", messages_buffer, serialize_json=True)

    messages_store: dict = Variable.get("messages_store", dict(), deserialize_json=True)
    if len(messages_store) == 0:
        Variable.set("messages_store", messages_store, serialize_json=True)


def consumer_function_batch(messages):
    Variable.get("messages_buffer", list(), deserialize_json=True)
    print(1, messages)
    messages_buffer = []
    for message in messages:
        key = json.loads(message.key())
        value = json.loads(message.value())
        messages_buffer.append(
            (
                key,
                value,
            )
        )

    Variable.set("messages_buffer", messages_buffer, serialize_json=True)


def consumer_function_batch_v2():
    import requests

    base_uri = "http://host.docker.internal:18082"
    consumer_name = "test_consumer"
    base_endpoint = f"{base_uri}/consumers/{KAFKA_GID}/instances/{consumer_name}"
    # create consumer
    res = requests.post(
        url=f"{base_uri}/consumers/{KAFKA_GID}",
        data=json.dumps(
            {
                "name": consumer_name,
                "format": "json",
                "auto.offset.reset": "earliest",
                "auto.commit.enable": "false",
                "fetch.min.bytes": "1",
                "consumer.request.timeout.ms": "5000",
            }
        ),
        headers={
            "Content-Type": "application/vnd.kafka.v2+json",
        },
        timeout=10_000,
    ).json()

    # subcribe consumer
    res = requests.post(
        url=f"{base_endpoint}/subscription",
        data=json.dumps(
            {
                "topics": [KAFKA_TOPIC],
            }
        ),
        headers={
            "Content-Type": "application/vnd.kafka.v2+json",
        },
        timeout=10_000,
    )
    # get records
    records = requests.get(
        url=f"{base_endpoint}/records",
        params={
            "timeout": 1000,
            "max_bytes": 100000,
        },
        headers={
            "Accept": "application/vnd.kafka.json.v2+json",
        },
        timeout=10_000,
    ).json()

    # commit offsets
    res = requests.post(
        url=f"{base_endpoint}/offsets",
        data=json.dumps(
            dict(
                partitions=dict(
                    topic=KAFKA_TOPIC,
                    partition=0,
                    offset=max(r["offset"] for r in records),
                ),
            )
        ),
        headers={"Content-Type": "application/vnd.kafka.v2+json"},
        timeout=10_000,
    )
    # delete consumer
    res = requests.delete(
        url=f"{base_endpoint}",
        headers={"Content-Type": "application/vnd.kafka.v2+json"},
        timeout=10_000,
    )

    print(len(records))

    return records


def map_vars_v2(records_str):
    records = json.loads(records_str)
    messages_store = Variable.get("messages_store", deserialize_json=True)

    print(1, records)

    triger_confs = []

    for message in records:
        service_who_sent = message["key"]
        payload = message["value"]
        curr_trigg_run_id = payload["s3_path"].replace("/", "")

        # next trigger task
        if payload["status"] == "init":
            curr_conf = {
                "trigger_run_id": curr_trigg_run_id,
                "conf": {
                    "service_who_sent": service_who_sent,
                },
            }
            triger_confs.append(curr_conf)

        # save in the global var
        if service_who_sent not in messages_store:
            messages_store[service_who_sent] = {
                curr_trigg_run_id: payload,
            }
        if curr_trigg_run_id not in messages_store[service_who_sent]:
            messages_store[service_who_sent][curr_trigg_run_id] = payload

        messages_store[service_who_sent][curr_trigg_run_id] = payload

    Variable.set("messages_store", messages_store, serialize_json=True)
    return triger_confs


with DAG(
    dag_id="030-demo-sensor-v2",
    description=__doc__,
    schedule="*/5 * * * *",
    # schedule="@once",
    max_active_runs=1,
    max_active_tasks=1,
    tags=["test"],
    start_date=datetime(2023, 10, 6),
    catchup=False,
) as dag:
    t0 = PythonOperator(
        task_id="load_connections",
        python_callable=load_connections,
    )

    t1 = PythonOperator(
        task_id="consume_topic",
        python_callable=consumer_function_batch_v2,
    )

    t2 = PythonOperator(
        task_id="map_var",
        python_callable=map_vars_v2,
        op_kwargs={
            "records_str": "{{ ti.xcom_pull() | tojson }}",
        },
    )

    t3 = TriggerDagRunOperator.partial(
        task_id="triger_sensor",
        trigger_dag_id="040-demo-sensor_app_a",
    ).expand_kwargs(t2.output.map(lambda x: x))

    t4 = EmptyOperator(
        task_id="allow_fails",
        trigger_rule=TriggerRule.ALL_DONE,
    )

    t5 = EmptyOperator(
        task_id="dont_allow_fails",
        trigger_rule=TriggerRule.ALL_SUCCESS,
    )

    t0 >> t1 >> t2 >> t3 >> t4
    t1 >> t5
