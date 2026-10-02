"""Catchup with a fixed start date, or catchup disabled."""

from datetime import datetime

import pendulum
from airflow import DAG
from shared.airflow_config import BASE_ARGS

default_args = {
    "owner": "data-team",
    "retries": 2,
    "start_date": pendulum.datetime(2026, 1, 1, tz="UTC"),
}

# Fixed start date: catchup creates a known, finite set of runs.
with DAG(
    "backfill_orders",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=True,
):
    pass

# start_date provided through default_args.
with DAG("sync_customers", schedule="@daily", default_args=default_args, catchup=True):
    pass

# Dynamic start date but catchup disabled: no backfill happens.
with DAG("sync_products", schedule="@daily", start_date=datetime.now(), catchup=False):
    pass

# start_date may be in imported default_args: the linter does not guess.
with DAG("sync_stock", schedule="@daily", default_args=BASE_ARGS, catchup=True):
    pass
