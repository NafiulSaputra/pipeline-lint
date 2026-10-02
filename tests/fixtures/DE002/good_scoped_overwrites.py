"""Overwrites that only replace the data this run is responsible for."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("daily_store_sales").getOrCreate()
run_date = spark.conf.get("pipeline.run_date")

daily_sales = spark.table("silver.orders").filter(F.col("order_date") == run_date)

# 1. Delta replaceWhere: only rows matching the predicate are replaced.
(
    daily_sales.write.format("delta")
    .mode("overwrite")
    .option("replaceWhere", f"order_date = '{run_date}'")
    .saveAsTable("gold.daily_sales")
)

# 2. Same, passed through options().
daily_sales.write.format("delta").mode("overwrite").options(
    replaceWhere=f"order_date = '{run_date}'"
).saveAsTable("gold.daily_sales_v2")

# 3. Dynamic partition overwrite for this write only.
(
    daily_sales.write.mode("overwrite")
    .option("partitionOverwriteMode", "dynamic")
    .partitionBy("order_date")
    .parquet("s3://analytics-bucket/daily_sales/")
)

# 4. DataFrameWriterV2: dynamic by design, or with an explicit condition.
daily_sales.writeTo("gold.daily_sales_v3").overwritePartitions()
daily_sales.writeTo("gold.daily_sales_v4").overwrite(F.col("order_date") == run_date)

# 5. Appends and streaming writes are not overwrites.
(
    spark.readStream.table("bronze.events")
    .writeStream.format("delta")
    .option("checkpointLocation", "/chk/events")
    .toTable("silver.events")
)
