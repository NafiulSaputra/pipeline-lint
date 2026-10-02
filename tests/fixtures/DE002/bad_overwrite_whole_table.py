"""Rebuild daily store sales for the current run date."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("daily_store_sales").getOrCreate()
run_date = spark.conf.get("pipeline.run_date")

daily_sales = (
    spark.table("silver.orders")
    .filter(F.col("order_date") == run_date)
    .groupBy("order_date", "store_id")
    .agg(F.sum("amount").alias("revenue"))
)

# Write today's partition of the sales table
daily_sales.write.format("delta").mode("overwrite").partitionBy("order_date").saveAsTable("gold.daily_sales")  # expect: DE002

# Refresh the store snapshot files
(
    daily_sales.write
    .mode("overwrite")  # expect: DE002
    .parquet("s3://analytics-bucket/store_snapshots/")
)

# Keep a history table in sync
daily_sales.write.insertInto("gold.daily_sales_history", overwrite=True)  # expect: DE002
