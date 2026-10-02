"""Sync DAGs that backfill missed runs."""

from datetime import datetime, timedelta

import pendulum
from airflow import DAG
from airflow.utils.dates import days_ago

default_args = {"owner": "data-team", "retries": 2}

with DAG(
    dag_id="backfill_orders",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime.now() - timedelta(days=7),
    catchup=True,  # expect: DE007
):
    pass

with DAG("sync_customers", schedule="@hourly", start_date=days_ago(2), catchup=True):  # expect: DE007
    pass

with DAG("sync_products", schedule="@daily", default_args=default_args, catchup=True):  # expect: DE007
    pass

start = pendulum.now("UTC")
with DAG("sync_stock", schedule="@daily", start_date=start, default_args=default_args, catchup=True):  # expect: DE007
    pass
