import functools
import json
import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
# This is just for setting up connections in the demo - you should use standard
# methods for setting these connections in production
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.amazon.aws.operators.s3 import S3ListOperator
from airflow.providers.apache.kafka.operators.consume import \
    ConsumeFromTopicOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.sensors.python import PythonSensor
from airflow.utils.trigger_rule import TriggerRule


def status(service_who_sent, _run_id):
    messages_store = Variable.get("messages_store", dict(), deserialize_json=True)

    curr_status = messages_store[service_who_sent][_run_id]["status"]

    print(1, curr_status)

    return curr_status == "end"


with DAG(
    dag_id="040-demo-sensor_app_a",
    description=__doc__,
    schedule=None,
    max_active_runs=4,
    max_active_tasks=4,
    tags=["test"],
    start_date=datetime(2023, 10, 6),
    catchup=True,
) as dag:
    t0 = PythonSensor(
        task_id="am-i-done",
        python_callable=status,
        op_kwargs={
            "service_who_sent": "{{ dag_run.conf['service_who_sent'] }}",
            "_run_id": "{{ run_id  }}",
        },
        mode="reschedule",
        poke_interval=90,
        exponential_backoff=True,
    )
