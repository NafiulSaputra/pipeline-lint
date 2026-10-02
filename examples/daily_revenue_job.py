"""Daily revenue job: an example of a pipeline written quickly with an AI assistant.

Run `pipeline-lint check examples/` to see what pipeline-lint reports for it.
More issues will be detected here as rules are added.
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("daily_revenue").getOrCreate()

orders = spark.table("raw.orders").filter(F.col("order_date") == "2026-01-01")

revenue = orders.groupBy("store_id").agg(F.sum("amount").alias("revenue"))

# Send the result to the reporting team
revenue.toPandas().to_csv("/tmp/daily_revenue.csv", index=False)

revenue.write.mode("append").saveAsTable("analytics.daily_revenue")
