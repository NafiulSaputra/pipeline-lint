-- Rebuild the store revenue mart for the run date.
-- Intended to refresh one day, but replaces every day in the table.
INSERT OVERWRITE TABLE gold.store_revenue  -- expect: DE002
SELECT store_id, order_date, SUM(amount) AS revenue
FROM silver.orders
WHERE order_date = '{{ ds }}'
GROUP BY store_id, order_date;
