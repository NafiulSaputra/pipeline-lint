"""Bronze-to-silver job for clickstream events."""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("clickstream_silver").getOrCreate()

raw_events = spark.read.json("s3://company-raw/clickstream/")

clean_events = (
    raw_events.filter(F.col("event_type").isNotNull())
    .withColumn("ingested_at", F.current_timestamp())
    .dropDuplicates(["event_id"])
)

# Save the cleaned events to the silver table
clean_events.write.format("delta").mode("append").saveAsTable("silver.events")  # expect: DE001

sessions = clean_events.groupBy("session_id").agg(F.count("*").alias("event_count"))
sessions.write.insertInto("silver.sessions")  # expect: DE001

daily_users = clean_events.select("user_id", F.to_date("event_ts").alias("event_date")).distinct()
daily_users.writeTo("gold.daily_active_users").append()  # expect: DE001

spark.sql(
    """
    INSERT INTO gold.event_counts  -- expect: DE001
    SELECT event_type, COUNT(*) AS events
    FROM silver.events
    GROUP BY event_type
    """
)
