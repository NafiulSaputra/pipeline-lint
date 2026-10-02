-- With dynamic mode, INSERT OVERWRITE only replaces the partitions present in the result.
SET spark.sql.sources.partitionOverwriteMode = dynamic;

INSERT OVERWRITE TABLE gold.store_revenue
SELECT store_id, SUM(amount) AS revenue, order_date
FROM silver.orders
WHERE order_date = '{{ ds }}'
GROUP BY store_id, order_date;
