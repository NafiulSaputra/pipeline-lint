"""Build a per-country revenue summary and export it for the finance team."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("revenue_summary").getOrCreate()

orders = spark.table("raw.orders").filter(F.col("status") == "completed")

# Get the list of customers so we can calculate each customer's total
customer_ids = [row["customer_id"] for row in orders.select("customer_id").distinct().collect()]  # expect: DE005

for customer_id in customer_ids:
    customer_orders = orders.filter(F.col("customer_id") == customer_id)
    # Global aggregate: one row, so this collect is fine
    total = customer_orders.agg(F.sum("amount")).collect()[0][0]
    print(f"{customer_id}: {total}")

# Export revenue by country to CSV
summary = orders.groupBy("country").agg(F.sum("amount").alias("revenue"))
summary.toPandas().to_csv("/dbfs/tmp/revenue_by_country.csv", index=False)  # expect: DE005

# Count customers per country
country_rows = (
    orders.groupBy("country")
    .agg(F.countDistinct("customer_id").alias("customers"))
    .collect()  # expect: DE005
)
