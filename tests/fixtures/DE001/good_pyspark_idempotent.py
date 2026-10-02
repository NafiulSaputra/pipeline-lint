"""Silver-layer loads written to be safe on retries and backfills."""

from delta.tables import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("orders_silver").getOrCreate()
run_date = spark.conf.get("pipeline.run_date")

orders = spark.table("bronze.orders").filter(F.col("order_date") == run_date)

# 1. Delete the processed window, then append it.
spark.sql(f"SELECT 1")  # f-strings are ignored
spark.sql("DELETE FROM silver.orders WHERE order_date = current_date()")
orders.write.mode("append").saveAsTable("silver.orders")

# 2. Overwrite only the processed partition.
(
    orders.write.format("delta")
    .mode("overwrite")
    .option("replaceWhere", "order_date = current_date()")
    .saveAsTable("silver.orders_by_day")
)

# 3. Upsert on the business key.
(
    DeltaTable.forName(spark, "silver.customers")
    .alias("t")
    .merge(orders.select("customer_id", "email").alias("s"), "t.customer_id = s.customer_id")
    .whenMatchedUpdateAll()
    .whenNotMatchedInsertAll()
    .execute()
)

# 4. insertInto with an explicit overwrite.
orders.write.insertInto("silver.orders_snapshot", overwrite=True)

# 5. Streaming append: exactly-once is guaranteed by the checkpoint.
(
    spark.readStream.table("bronze.events")
    .writeStream.format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/chk/silver_events")
    .toTable("silver.events_stream")
)

# 6. MERGE through SQL, with the query in a variable.
merge_query = """
MERGE INTO silver.products AS t
USING bronze.products AS s ON t.product_id = s.product_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
"""
spark.sql(merge_query)

# 7. Python list.append is not a Spark write.
loaded_tables = []
loaded_tables.append("silver.orders")
