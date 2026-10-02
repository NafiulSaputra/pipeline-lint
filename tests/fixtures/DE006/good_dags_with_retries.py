"""DAGs with retries configured, written for Airflow 3."""

from datetime import timedelta

import pendulum
from airflow.sdk import DAG, dag, task
from shared.airflow_config import BASE_ARGS

RETRIES = 2
START = pendulum.datetime(2026, 1, 1, tz="UTC")

default_args = {
    "owner": "data-team",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}

with DAG(dag_id="ingest_orders", default_args=default_args, schedule="@daily", start_date=START):
    pass


@dag(schedule="@daily", start_date=START, default_args=dict(owner="data-team", retries=RETRIES))
def ingest_events():
    @task
    def load():
        print("load")

    load()


# default_args the linter cannot see: imported, or merged from an imported base.
with DAG(dag_id="ingest_customers", default_args=BASE_ARGS, schedule="@daily", start_date=START):
    pass

with DAG(
    dag_id="ingest_products",
    default_args={**BASE_ARGS, "owner": "catalog-team"},
    schedule="@daily",
    start_date=START,
):
    pass
