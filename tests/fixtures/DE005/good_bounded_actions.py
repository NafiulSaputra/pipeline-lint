"""Incremental load helpers that only move small, bounded results to the driver."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("events_incremental").getOrCreate()

events = spark.table("raw.events")

# High-water mark: a global aggregate always returns exactly one row
last_loaded = events.agg(F.max("event_ts")).collect()[0][0]

# Bounded through a variable
preview = events.limit(20)
preview_rows = preview.collect()

# Bounded in the same chain
sample_pdf = events.orderBy(F.col("event_ts").desc()).limit(1000).toPandas()

# Actions that are bounded by design
first_event = events.first()
some_events = events.take(5)
total_events = events.count()
