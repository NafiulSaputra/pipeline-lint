-- Idempotent loading patterns: each statement gives the same result on every re-run.

-- 1. Delete the processed window, then insert it again.
DELETE FROM analytics.fct_orders WHERE order_date = '{{ ds }}';

INSERT INTO analytics.fct_orders
SELECT order_id, customer_id, amount, order_date
FROM raw.orders
WHERE order_date = '{{ ds }}';

-- 2. Unqualified DELETE target matches the qualified INSERT target.
TRUNCATE TABLE stg_customers;

INSERT INTO staging.stg_customers
SELECT customer_id, email, country FROM raw.customers;

-- 3. Overwrite a single partition.
INSERT OVERWRITE TABLE analytics.daily_revenue PARTITION (revenue_date = '{{ ds }}')
SELECT store_id, SUM(amount) AS revenue
FROM analytics.fct_orders
WHERE order_date = '{{ ds }}'
GROUP BY store_id;

-- 4. Upsert on the business key.
MERGE INTO analytics.dim_customers AS t
USING staging.stg_customers AS s
ON t.customer_id = s.customer_id
WHEN MATCHED THEN UPDATE SET t.email = s.email, t.country = s.country
WHEN NOT MATCHED THEN INSERT (customer_id, email, country) VALUES (s.customer_id, s.email, s.country);
