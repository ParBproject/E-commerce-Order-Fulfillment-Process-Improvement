-- SQL Queries for Process Improvement Analysis
-- E-commerce Order Fulfillment Data Analysis
-- ================================================

-- Query 1: Calculate average cycle time by state (Before vs After)
-- ================================================================
WITH before_orders AS (
    SELECT 
        'Before' as state,
        AVG(total_cycle_time_minutes) as avg_cycle_time,
        STDDEV(total_cycle_time_minutes) as stddev_cycle_time,
        MIN(total_cycle_time_minutes) as min_cycle_time,
        MAX(total_cycle_time_minutes) as max_cycle_time,
        COUNT(*) as total_orders
    FROM before_state_orders
),
after_orders AS (
    SELECT 
        'After' as state,
        AVG(total_cycle_time_minutes) as avg_cycle_time,
        STDDEV(total_cycle_time_minutes) as stddev_cycle_time,
        MIN(total_cycle_time_minutes) as min_cycle_time,
        MAX(total_cycle_time_minutes) as max_cycle_time,
        COUNT(*) as total_orders
    FROM after_state_orders
)
SELECT * FROM before_orders
UNION ALL
SELECT * FROM after_orders;


-- Query 2: Calculate error rates and rework rates
-- ================================================
SELECT 
    'Before' as state,
    SUM(total_errors) * 1.0 / COUNT(*) as avg_errors_per_order,
    SUM(CASE WHEN total_errors > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as error_rate_pct,
    SUM(rework_required) * 100.0 / COUNT(*) as rework_rate_pct
FROM before_state_orders

UNION ALL

SELECT 
    'After' as state,
    SUM(total_errors) * 1.0 / COUNT(*) as avg_errors_per_order,
    SUM(CASE WHEN total_errors > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as error_rate_pct,
    SUM(rework_required) * 100.0 / COUNT(*) as rework_rate_pct
FROM after_state_orders;


-- Query 3: Analyze bottlenecks - identify slowest process steps
-- ==============================================================
SELECT 
    'Validation' as process_step,
    AVG(validation_time) as avg_time_before,
    (SELECT AVG(validation_time) FROM after_state_orders) as avg_time_after,
    AVG(validation_time) - (SELECT AVG(validation_time) FROM after_state_orders) as time_saved
FROM before_state_orders

UNION ALL

SELECT 
    'Inventory Check',
    AVG(inventory_time),
    (SELECT AVG(inventory_time) FROM after_state_orders),
    AVG(inventory_time) - (SELECT AVG(inventory_time) FROM after_state_orders)
FROM before_state_orders

UNION ALL

SELECT 
    'Payment Processing',
    AVG(payment_time),
    (SELECT AVG(payment_time) FROM after_state_orders),
    AVG(payment_time) - (SELECT AVG(payment_time) FROM after_state_orders)
FROM before_state_orders

UNION ALL

SELECT 
    'Picking & Packing',
    AVG(picking_time),
    (SELECT AVG(picking_time) FROM after_state_orders),
    AVG(picking_time) - (SELECT AVG(picking_time) FROM after_state_orders)
FROM before_state_orders

UNION ALL

SELECT 
    'QC Check',
    AVG(qc_time),
    (SELECT AVG(qc_time) FROM after_state_orders),
    AVG(qc_time) - (SELECT AVG(qc_time) FROM after_state_orders)
FROM before_state_orders

ORDER BY time_saved DESC;


-- Query 4: Calculate daily throughput capacity
-- =============================================
WITH metrics AS (
    SELECT 
        'Before' as state,
        AVG(total_cycle_time_minutes) as avg_cycle_time,
        (8 * 60) / AVG(total_cycle_time_minutes) as orders_per_day
    FROM before_state_orders
    
    UNION ALL
    
    SELECT 
        'After' as state,
        AVG(total_cycle_time_minutes) as avg_cycle_time,
        (8 * 60) / AVG(total_cycle_time_minutes) as orders_per_day
    FROM after_state_orders
)
SELECT 
    state,
    ROUND(avg_cycle_time, 2) as avg_cycle_time_min,
    ROUND(orders_per_day, 1) as orders_per_8hr_day,
    ROUND((orders_per_day * 22), 0) as orders_per_month,
    ROUND((orders_per_day * 260), 0) as orders_per_year
FROM metrics;


-- Query 5: Identify problematic order patterns (high error orders)
-- =================================================================
SELECT 
    order_id,
    total_cycle_time_minutes,
    total_errors,
    rework_required,
    CASE 
        WHEN total_errors >= 2 THEN 'High Error'
        WHEN total_errors = 1 THEN 'Medium Error'
        ELSE 'No Error'
    END as error_category
FROM before_state_orders
WHERE total_errors > 0 OR rework_required = 1
ORDER BY total_cycle_time_minutes DESC
LIMIT 20;


-- Query 6: Calculate cost savings potential
-- ==========================================
WITH savings AS (
    SELECT 
        AVG(b.total_cycle_time_minutes) - AVG(a.total_cycle_time_minutes) as time_saved_per_order_min,
        1000 as monthly_order_volume,
        25 as hourly_labor_cost
    FROM before_state_orders b
    CROSS JOIN after_state_orders a
)
SELECT 
    time_saved_per_order_min as minutes_saved_per_order,
    time_saved_per_order_min / 60 as hours_saved_per_order,
    (time_saved_per_order_min / 60 * monthly_order_volume) as monthly_hours_saved,
    (time_saved_per_order_min / 60 * monthly_order_volume * hourly_labor_cost) as monthly_cost_savings,
    (time_saved_per_order_min / 60 * monthly_order_volume * hourly_labor_cost * 12) as annual_cost_savings
FROM savings;


-- Query 7: Process step contribution to total time (Before)
-- ==========================================================
SELECT 
    ROUND(AVG(validation_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as validation_pct,
    ROUND(AVG(inventory_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as inventory_pct,
    ROUND(AVG(payment_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as payment_pct,
    ROUND(AVG(picking_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as picking_pct,
    ROUND(AVG(qc_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as qc_pct,
    ROUND(AVG(shipping_time) * 100.0 / AVG(total_cycle_time_minutes), 1) as shipping_pct
FROM before_state_orders;


-- Query 8: Improvement percentage by KPI
-- =======================================
SELECT 
    'Cycle Time' as kpi,
    ROUND(AVG(b.total_cycle_time_minutes), 1) as before_value,
    ROUND(AVG(a.total_cycle_time_minutes), 1) as after_value,
    ROUND((AVG(b.total_cycle_time_minutes) - AVG(a.total_cycle_time_minutes)) * 100.0 / AVG(b.total_cycle_time_minutes), 1) as improvement_pct
FROM before_state_orders b
CROSS JOIN after_state_orders a

UNION ALL

SELECT 
    'Error Rate',
    ROUND(SUM(b.total_errors) * 100.0 / COUNT(*), 1),
    ROUND(SUM(a.total_errors) * 100.0 / COUNT(*), 1),
    ROUND((SUM(b.total_errors) * 100.0 / COUNT(*) - SUM(a.total_errors) * 100.0 / COUNT(*)) * 100.0 / (SUM(b.total_errors) * 100.0 / COUNT(*)), 1)
FROM before_state_orders b
CROSS JOIN after_state_orders a

UNION ALL

SELECT 
    'Rework Rate',
    ROUND(SUM(b.rework_required) * 100.0 / COUNT(*), 1),
    ROUND(SUM(a.rework_required) * 100.0 / COUNT(*), 1),
    ROUND((SUM(b.rework_required) * 100.0 / COUNT(*) - SUM(a.rework_required) * 100.0 / COUNT(*)) * 100.0 / (SUM(b.rework_required) * 100.0 / COUNT(*)), 1)
FROM before_state_orders b
CROSS JOIN after_state_orders a;


-- Query 9: Top 10 orders with longest cycle times (Before vs After)
-- ==================================================================
SELECT 'Before' as state, order_id, total_cycle_time_minutes, total_errors, rework_required
FROM before_state_orders
ORDER BY total_cycle_time_minutes DESC
LIMIT 10

UNION ALL

SELECT 'After', order_id, total_cycle_time_minutes, total_errors, rework_required
FROM after_state_orders
ORDER BY total_cycle_time_minutes DESC
LIMIT 10;


-- Query 10: Monthly trend analysis (if dates available)
-- ======================================================
SELECT 
    DATE_TRUNC('month', order_date) as month,
    COUNT(*) as total_orders,
    AVG(total_cycle_time_minutes) as avg_cycle_time,
    SUM(total_errors) as total_errors,
    SUM(rework_required) as total_rework
FROM before_state_orders
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month;

-- ================================================
-- End of SQL Analysis Queries
-- ================================================

/*
NOTES ON USAGE:
- These queries assume tables named 'before_state_orders' and 'after_state_orders'
- Adjust table names based on your actual database schema
- Add appropriate indexes on columns used in WHERE/JOIN clauses for performance
- Queries use standard SQL syntax; may need minor adjustments for specific databases (MySQL, PostgreSQL, SQL Server)
- All calculations use proper handling of NULL values
- Percentages are rounded to 1 decimal place for readability
*/
