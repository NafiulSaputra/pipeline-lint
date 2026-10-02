"""Explicit column selection before writing."""

from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("copy_orders").getOrCreate()
staged = spark.table("staging.orders")

staged.select("order_id", "customer_id", "amount").write.saveAsTable("analytics.orders_copy")

# select("*") that is only inspected, never written.
staged.select("*").show(10)
row_count = staged.select("*").count()

spark.sql("SELECT * FROM staging.orders LIMIT 5").show()
