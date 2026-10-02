-- Daily load: completed orders from the previous day into the reporting tables.
-- Scheduled by Airflow; {{ ds }} is the run's logical date.

INSERT INTO analytics.fct_orders  -- expect: DE001
SELECT
    o.order_id,
    o.customer_id,
    o.amount,
    o.order_date
FROM raw.orders AS o
WHERE o.status = 'completed'
  AND o.order_date = '{{ ds }}';

-- Clears a *different* table, so it does not make the refunds load idempotent.
DELETE FROM analytics.fct_payments WHERE payment_date = '{{ ds }}';

INSERT INTO analytics.fct_refunds (refund_id, order_id, amount, refund_date)  -- expect: DE001
SELECT refund_id, order_id, amount, refund_date
FROM raw.refunds
WHERE refund_date = '{{ ds }}';
