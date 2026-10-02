-- Explicit columns on both sides.
INSERT INTO analytics.fct_orders (order_id, customer_id, amount, order_date)
SELECT order_id, customer_id, amount, order_date
FROM staging.orders
WHERE order_date = '{{ ds }}';

-- Stars that do not decide the written columns.
INSERT INTO analytics.active_customers
SELECT o.customer_id, COUNT(*) AS order_count
FROM (SELECT * FROM staging.orders) AS o
WHERE EXISTS (SELECT * FROM silver.customers AS c WHERE c.customer_id = o.customer_id)
GROUP BY o.customer_id;

CREATE TABLE analytics.customer_emails AS
SELECT customer_id, email FROM silver.customers;

-- Exploration and views are not table writes.
SELECT * FROM staging.orders LIMIT 10;

CREATE OR REPLACE VIEW analytics.v_orders AS SELECT * FROM staging.orders;

-- Delta MERGE actions match columns by name.
MERGE INTO analytics.dim_products AS t
USING staging.products AS s
ON t.product_id = s.product_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
