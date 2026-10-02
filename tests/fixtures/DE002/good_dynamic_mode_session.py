"""Session-wide dynamic partition overwrite: every overwrite only touches written partitions."""

from pyspark.sql import SparkSession

spark = (
    SparkSession.builder.appName("partitioned_loads")
    .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
    .getOrCreate()
)

daily = spark.table("silver.orders")
daily.write.mode("overwrite").insertInto("gold.daily_orders")
daily.write.insertInto("gold.daily_orders_copy", overwrite=True)
spark.sql("INSERT OVERWRITE TABLE gold.daily_totals SELECT order_date, COUNT(*) FROM silver.orders GROUP BY order_date")
