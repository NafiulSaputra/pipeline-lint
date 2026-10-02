-- Example SQL load, written the way an assistant often first suggests it.
INSERT INTO analytics.fct_orders
SELECT *
FROM raw.orders
WHERE order_date = '2026-01-01';
