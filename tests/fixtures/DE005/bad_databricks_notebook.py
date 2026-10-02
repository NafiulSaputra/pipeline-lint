# Databricks notebook source
# MAGIC %md
# MAGIC # Daily sales export
# MAGIC Exports today's sales to Excel for the regional managers.

# COMMAND ----------

sales = spark.table("analytics.daily_sales").where("sale_date = current_date()")

# COMMAND ----------

pdf = sales.toPandas()  # expect: DE005
pdf.to_excel("/dbfs/FileStore/exports/daily_sales.xlsx", index=False)

# COMMAND ----------

# A bounded preview is fine
display(sales.limit(20))
preview_rows = sales.limit(100).collect()
