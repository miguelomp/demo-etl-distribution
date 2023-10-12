from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.utils.trigger_rule import TriggerRule


def create_user():
    import uuid

    import requests
    import random

    responses = []
    for i in range(random.randint(1, 5)):

        response = requests.post(
            url="http://host.docker.internal/pipeline/api/users/",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "email": f"{uuid.uuid4()}@someemail.com",
                "password": f"{uuid.uuid4()}",
            },
            auth=('admin', 'admin'),
            timeout=30,
            verify=False,
        )

        responses.append(response.text)

    return responses


with DAG(
    dag_id="000-demo-insert-db",
    description=__doc__,
    schedule="* * * * *",
    max_active_runs=1,
    max_active_tasks=1,
    tags=["test"],
    start_date=datetime(2023, 10, 4),
    catchup=False,
) as dag:
    t1 = PythonOperator(
        task_id="t1",
        python_callable=create_user,
    )
