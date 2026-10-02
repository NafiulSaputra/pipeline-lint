-- Copy the run date's orders into the reporting table.
INSERT INTO analytics.fct_orders  -- expect: DE004
SELECT *
FROM staging.orders
WHERE order_date = '{{ ds }}';

-- Snapshot of the customer dimension.
CREATE OR REPLACE TABLE analytics.dim_customers_snapshot AS  -- expect: DE004
SELECT c.*
FROM silver.customers AS c;

-- Combine on-time and late events for the day.
INSERT OVERWRITE TABLE analytics.events_daily PARTITION (event_date = '{{ ds }}')  -- expect: DE004
SELECT event_id, user_id, event_type FROM staging.events
UNION ALL
SELECT * FROM staging.late_events;
