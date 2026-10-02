"""Q1 order analysis job."""

from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("q1_orders").getOrCreate()
orders = spark.table("silver.orders")

recent = orders.filter(F.col("order_date") >= "2026-01-01")  # expect: DE003
q1 = orders.where("order_date BETWEEN '2026-01-01' AND '2026-03-31'")  # expect: DE003
january = orders.filter(
    F.col("order_date").between(F.lit("2026-01-01"), F.lit("2026-01-31"))  # expect: DE003
)
since_launch = orders.filter(F.col("created_at") > datetime(2025, 11, 1))  # expect: DE003

spark.sql("SELECT * FROM silver.orders WHERE order_date = '2026-02-01'")  # expect: DE003
