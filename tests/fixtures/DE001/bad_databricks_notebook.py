# Databricks notebook source
# MAGIC %md
# MAGIC ## Load yesterday's orders
# MAGIC Appends yesterday's completed orders to the daily table.

# COMMAND ----------

# MAGIC %sql
# MAGIC INSERT INTO analytics.orders_daily  -- expect: DE001
# MAGIC SELECT order_id, customer_id, amount, order_date
# MAGIC FROM raw.orders
# MAGIC WHERE status = 'completed'
# MAGIC   AND order_date = date_sub(current_date(), 1)

# COMMAND ----------

summary = spark.table("analytics.orders_daily").groupBy("order_date").count()
summary.write.mode("append").saveAsTable("analytics.orders_daily_summary")  # expect: DE001
