"""Airflow DAG that runs the daily revenue job: an example with typical first-draft settings."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "data-team",
    "email_on_failure": True,
}

with DAG(
    dag_id="daily_revenue",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime.now() - timedelta(days=30),
    catchup=True,
) as dag:
    BashOperator(
        task_id="run_daily_revenue_job",
        bash_command="spark-submit examples/daily_revenue_job.py",
    )
