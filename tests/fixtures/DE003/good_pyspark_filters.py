"""Filters driven by job parameters or computed dates."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("daily_orders").getOrCreate()
run_date = spark.conf.get("pipeline.run_date")
orders = spark.table("silver.orders")

daily = orders.filter(F.col("order_date") == run_date)
last_week = orders.filter(F.col("order_date") >= F.date_sub(F.current_date(), 7))
current_rows = orders.where(F.col("valid_to") == "9999-12-31")
by_day = orders.filter(F.date_format("order_date", "yyyy-MM-dd") == run_date)

# A literal date outside a filter is not this rule's concern.
tagged = orders.withColumn("schema_version_date", F.lit("2026-01-01"))

spark.sql(f"SELECT * FROM silver.orders WHERE order_date = '{run_date}'")
