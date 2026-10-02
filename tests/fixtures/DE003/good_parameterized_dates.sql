-- Dates come from the orchestrator or are computed at run time.
SELECT customer_id, email
FROM silver.dim_customers
WHERE valid_to = '9999-12-31'
  AND updated_at >= date_sub(current_date(), 7)
  AND snapshot_date = '{{ ds }}'
  AND event_date BETWEEN '{{ data_interval_start }}' AND '{{ data_interval_end }}';

-- Date literals outside filters are not flagged.
SELECT
    order_id,
    CASE WHEN order_date < '2020-01-01' THEN 'legacy' ELSE 'current' END AS era,
    date_format(order_date, 'yyyy-MM-dd') AS order_day
FROM silver.orders
WHERE order_id <> '2026-99-99';
