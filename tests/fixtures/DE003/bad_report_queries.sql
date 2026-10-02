-- Weekly revenue report, first draft.
SELECT
    store_id,
    SUM(amount) AS revenue
FROM silver.orders
WHERE order_date >= '2026-01-01'  -- expect: DE003
  AND order_date < DATE '2026-01-08'  -- expect: DE003
  AND status = 'completed'
GROUP BY store_id
HAVING MAX(updated_at) > '2026-01-07 23:59:59';  -- expect: DE003

-- Orders paid in January.
SELECT o.order_id, p.payment_id
FROM silver.orders AS o
JOIN silver.payments AS p
  ON p.order_id = o.order_id
 AND p.paid_at BETWEEN '2026-01-01T00:00:00Z' AND '2026-01-31T23:59:59Z'  -- expect: DE003
WHERE o.region IN ('EU', 'US');

-- Specific campaign days.
SELECT COUNT(*) AS signups
FROM silver.users
WHERE signup_date IN ('2026-02-14', '2026-03-08');  -- expect: DE003
