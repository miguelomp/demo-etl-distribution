import json
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.utils.trigger_rule import TriggerRule
import functools
import json
import logging
from datetime import datetime, timedelta

from airflow import DAG

# This is just for setting up connections in the demo - you should use standard
# methods for setting these connections in production
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.amazon.aws.operators.s3 import S3ListOperator
from airflow.providers.apache.kafka.operators.produce import ProduceToTopicOperator

KAFKA_CONN_ID = "t1-3"
S3_CONN_ID = "s3conn"
# TODO bring S3_BUCKET_NAME from docker compose deployed, it is already defined in the .env file
S3_BUCKET_NAME = "data-dump"
S3_PREFIX = "dev/XX_DB/{{ data_interval_start - macros.timedelta(minutes=20) }}_{{ data_interval_end - macros.timedelta(minutes=20) }}"


def load_connections():
    # Connections needed for this example dag to finish
    from airflow.models import Connection, Variable
    from airflow.utils import db

    db.merge_conn(
        Connection(
            conn_id=S3_CONN_ID,
            conn_type="aws",
            login=Variable.get("aws_access_key_id"),
            password=Variable.get("aws_secret_access_key"),
            extra={
                # Specify extra parameters here
                "region_name": "us-west-2",
            },
        )
    )

    db.merge_conn(
        Connection(
            conn_id=KAFKA_CONN_ID,
            conn_type="kafka",
            extra=json.dumps(
                {
                    "socket.timeout.ms": 10,
                    "bootstrap.servers": "redpanda:9092",
                }
            ),
        )
    )


def get_users(start_date, end_date):
    import requests

    response = requests.get(
        url="http://host.docker.internal/pipeline/api/users/",
        params={
            "start_date": start_date,
            "end_date": end_date,
        },
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
        },
        auth=("admin", "admin"),
        timeout=30,
        verify=False,
    )

    return json.dumps(response.json())


def write_to_s3(connid: str, content: str, s3_key: str):
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook

    hook = S3Hook(aws_conn_id=connid)
    client = hook.get_conn()

    client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=s3_key,
        Body=content.encode(),
    )


def producer_function(s3_key: str):
    yield ("airflow", json.dumps({"s3_path": s3_key}))


with DAG(
    dag_id="010-demo-extract-daily",
    description=__doc__,
    schedule="*/5 * * * *",
    max_active_runs=1,
    max_active_tasks=1,
    tags=["test"],
    start_date=datetime(2023, 10, 5),
    catchup=False,
) as dag:
    t0 = PythonOperator(
        task_id="load_connections",
        python_callable=load_connections,
    )

    t1 = PythonOperator(
        task_id="t1",
        python_callable=get_users,
        op_kwargs={
            "start_date": "{{ data_interval_start - macros.timedelta(minutes=20) }}",
            "end_date": "{{ data_interval_end - macros.timedelta(minutes=20) }}",
        },
    )

    t2 = ShortCircuitOperator(
        task_id="something_to_do",
        python_callable=lambda items: len(json.loads(items)) > 0,
        op_args=("{{ ti.xcom_pull() }}",),
    )

    t3 = PythonOperator(
        task_id="t3",
        python_callable=write_to_s3,
        op_kwargs={
            "connid": S3_CONN_ID,
            "content": "{{ ti.xcom_pull() }}",
            "s3_key": f"{S3_PREFIX}/data.txt",
        },
    )

    t4 = ProduceToTopicOperator(
        kafka_config_id=KAFKA_CONN_ID,
        task_id="produce_to_topic",
        topic="dbp-created-at",
        producer_function=producer_function,
        producer_function_kwargs={
            "s3_key": S3_PREFIX,
        },
    )

    t0 >> t1 >> t2 >> t3 >> t4
