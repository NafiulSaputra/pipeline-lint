-- Replace only the partition for the run date.
INSERT OVERWRITE TABLE gold.store_revenue PARTITION (order_date = '{{ ds }}')
SELECT store_id, SUM(amount) AS revenue
FROM silver.orders
WHERE order_date = '{{ ds }}'
GROUP BY store_id;

-- Plain INSERT INTO is DE001's concern, not DE002's.
INSERT INTO gold.load_log VALUES ('store_revenue', '{{ ds }}');
