"""Daily ingestion DAGs."""

from datetime import datetime

from airflow import DAG
from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "email_on_failure": True,
}

with DAG(  # expect: DE006
    dag_id="ingest_orders",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
) as orders_dag:
    BashOperator(task_id="load_orders", bash_command="python load_orders.py")


@dag(  # expect: DE006
    schedule="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"owner": "data-team", "retries": 0},
)
def ingest_events():
    @task
    def load_events():
        print("loading events")

    load_events()


ingest_events()

payments_dag = DAG("ingest_payments", schedule="@daily", start_date=datetime(2026, 1, 1))  # expect: DE006
