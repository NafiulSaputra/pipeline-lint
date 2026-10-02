"""Copy staged orders into the analytics layer."""

from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("copy_orders").getOrCreate()
staged = spark.table("staging.orders")

staged.select("*").write.format("delta").mode("overwrite").saveAsTable("analytics.orders_copy")  # expect: DE004

staged.alias("o").select("o.*").writeTo("analytics.orders_v2").createOrReplace()  # expect: DE004

spark.sql("INSERT INTO analytics.orders_archive SELECT * FROM staging.orders")  # expect: DE004
