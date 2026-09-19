-- E-commerce Fulfillment Analytics Model (DuckDB)
-- =================================================
-- Reproducible analytical layer over the case-study CSV files.
-- Demonstrates: CTEs, conditional aggregation, window functions,
-- percentile ranking, rolling metrics, lateral VALUES, and reusable views.

CREATE OR REPLACE VIEW before_orders AS
SELECT
    'Before'::VARCHAR AS state,
    *
FROM read_csv_auto('before_state_data.csv', header = true);

CREATE OR REPLACE VIEW after_orders AS
SELECT
    'After'::VARCHAR AS state,
    *
FROM read_csv_auto('after_state_data.csv', header = true);

CREATE OR REPLACE VIEW orders AS
SELECT * FROM before_orders
UNION ALL
SELECT * FROM after_orders;


-- 1) Data-quality controls
-- ------------------------
CREATE OR REPLACE VIEW data_quality_report AS
WITH duplicate_ids AS (
    SELECT
        state,
        order_id,
        COUNT(*) AS duplicate_count
    FROM orders
    GROUP BY state, order_id
    HAVING COUNT(*) > 1
),
quality AS (
    SELECT
        state,
        COUNT(*) AS row_count,
        SUM(
            CASE
                WHEN order_id IS NULL
                  OR order_date IS NULL
                  OR total_cycle_time_minutes IS NULL
                THEN 1 ELSE 0
            END
        ) AS rows_with_required_nulls,
        SUM(CASE WHEN total_cycle_time_minutes <= 0 THEN 1 ELSE 0 END)
            AS invalid_cycle_times,
        SUM(CASE WHEN rework_required NOT IN (0, 1) THEN 1 ELSE 0 END)
            AS invalid_rework_flags
    FROM orders
    GROUP BY state
),
duplicates AS (
    SELECT state, COALESCE(SUM(duplicate_count - 1), 0) AS duplicate_order_ids
    FROM duplicate_ids
    GROUP BY state
)
SELECT
    q.*,
    COALESCE(d.duplicate_order_ids, 0) AS duplicate_order_ids
FROM quality q
LEFT JOIN duplicates d USING (state);


-- 2) Executive KPI scorecard
-- --------------------------
CREATE OR REPLACE VIEW state_kpis AS
SELECT
    state,
    COUNT(*) AS orders,
    AVG(total_cycle_time_minutes) AS avg_cycle_time,
    MEDIAN(total_cycle_time_minutes) AS median_cycle_time,
    QUANTILE_CONT(total_cycle_time_minutes, 0.90) AS p90_cycle_time,
    AVG(CASE WHEN total_errors > 0 THEN 1.0 ELSE 0.0 END) AS error_rate,
    AVG(CASE WHEN rework_required > 0 THEN 1.0 ELSE 0.0 END) AS rework_rate,
    480.0 / AVG(total_cycle_time_minutes) AS orders_per_8h_day,
    22.0 * 480.0 / AVG(total_cycle_time_minutes) AS monthly_capacity
FROM orders
GROUP BY state;


-- 3) Before/after improvement table with direction-aware calculations
-- ------------------------------------------------------------------
CREATE OR REPLACE VIEW kpi_improvement AS
WITH p AS (
    SELECT
        MAX(avg_cycle_time) FILTER (WHERE state = 'Before') AS before_cycle,
        MAX(avg_cycle_time) FILTER (WHERE state = 'After') AS after_cycle,
        MAX(p90_cycle_time) FILTER (WHERE state = 'Before') AS before_p90,
        MAX(p90_cycle_time) FILTER (WHERE state = 'After') AS after_p90,
        MAX(error_rate) FILTER (WHERE state = 'Before') AS before_error,
        MAX(error_rate) FILTER (WHERE state = 'After') AS after_error,
        MAX(rework_rate) FILTER (WHERE state = 'Before') AS before_rework,
        MAX(rework_rate) FILTER (WHERE state = 'After') AS after_rework,
        MAX(orders_per_8h_day) FILTER (WHERE state = 'Before') AS before_throughput,
        MAX(orders_per_8h_day) FILTER (WHERE state = 'After') AS after_throughput
    FROM state_kpis
)
SELECT
    'Average Cycle Time' AS metric,
    before_cycle AS before_value,
    after_cycle AS after_value,
    (before_cycle - after_cycle) / NULLIF(before_cycle, 0) AS improvement
FROM p
UNION ALL
SELECT
    'P90 Cycle Time',
    before_p90,
    after_p90,
    (before_p90 - after_p90) / NULLIF(before_p90, 0)
FROM p
UNION ALL
SELECT
    'Error Rate',
    before_error,
    after_error,
    (before_error - after_error) / NULLIF(before_error, 0)
FROM p
UNION ALL
SELECT
    'Rework Rate',
    before_rework,
    after_rework,
    (before_rework - after_rework) / NULLIF(before_rework, 0)
FROM p
UNION ALL
SELECT
    'Orders / 8h Day',
    before_throughput,
    after_throughput,
    (after_throughput - before_throughput) / NULLIF(before_throughput, 0)
FROM p;


-- 4) Tidy process-step view
-- -------------------------
CREATE OR REPLACE VIEW process_steps AS
SELECT
    o.state,
    o.order_id,
    o.order_date,
    step.process_step,
    step.minutes
FROM orders o
CROSS JOIN LATERAL (
    VALUES
        ('Validation', o.validation_time),
        ('Inventory', o.inventory_time),
        ('Payment', o.payment_time),
        ('Picking & Packing', o.picking_time),
        ('Quality Control', o.qc_time),
        ('Shipping', o.shipping_time)
) AS step(process_step, minutes);


-- 5) Step-level comparison
-- ------------------------
CREATE OR REPLACE VIEW process_step_summary AS
SELECT
    process_step,
    AVG(minutes) FILTER (WHERE state = 'Before') AS before_avg_minutes,
    AVG(minutes) FILTER (WHERE state = 'After') AS after_avg_minutes,
    AVG(minutes) FILTER (WHERE state = 'Before')
      - AVG(minutes) FILTER (WHERE state = 'After') AS minutes_saved
FROM process_steps
GROUP BY process_step
ORDER BY minutes_saved DESC;


-- 6) Pareto analysis using windows
-- -------------------------------
CREATE OR REPLACE VIEW bottleneck_pareto AS
WITH step_average AS (
    SELECT
        state,
        process_step,
        AVG(minutes) AS avg_minutes
    FROM process_steps
    GROUP BY state, process_step
),
ranked AS (
    SELECT
        state,
        process_step,
        avg_minutes,
        RANK() OVER (
            PARTITION BY state
            ORDER BY avg_minutes DESC
        ) AS bottleneck_rank,
        avg_minutes
          / SUM(avg_minutes) OVER (PARTITION BY state) AS step_share
    FROM step_average
)
SELECT
    *,
    SUM(step_share) OVER (
        PARTITION BY state
        ORDER BY bottleneck_rank
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_share
FROM ranked
ORDER BY state, bottleneck_rank;


-- 7) Daily operations with rolling 7-day cycle-time average
-- ---------------------------------------------------------
CREATE OR REPLACE VIEW daily_operations AS
WITH daily AS (
    SELECT
        state,
        CAST(order_date AS DATE) AS order_date,
        COUNT(*) AS orders,
        AVG(total_cycle_time_minutes) AS avg_cycle_time,
        QUANTILE_CONT(total_cycle_time_minutes, 0.90) AS p90_cycle_time,
        AVG(CASE WHEN total_errors > 0 THEN 1.0 ELSE 0.0 END) AS error_rate,
        AVG(CASE WHEN rework_required > 0 THEN 1.0 ELSE 0.0 END) AS rework_rate
    FROM orders
    GROUP BY state, CAST(order_date AS DATE)
)
SELECT
    *,
    AVG(avg_cycle_time) OVER (
        PARTITION BY state
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS cycle_time_7d_avg
FROM daily
ORDER BY state, order_date;


-- 8) Exception ranking using percentile windows
-- ---------------------------------------------
CREATE OR REPLACE VIEW order_exceptions AS
WITH scored AS (
    SELECT
        *,
        PERCENT_RANK() OVER (
            PARTITION BY state
            ORDER BY total_cycle_time_minutes
        ) AS cycle_percentile
    FROM orders
)
SELECT
    state,
    order_id,
    order_date,
    total_cycle_time_minutes,
    total_errors,
    rework_required,
    cycle_percentile,
    0.60 * cycle_percentile
      + 0.25 * CASE WHEN total_errors > 0 THEN 1.0 ELSE 0.0 END
      + 0.15 * CASE WHEN rework_required > 0 THEN 1.0 ELSE 0.0 END
        AS exception_score
FROM scored
ORDER BY state, exception_score DESC;


-- 9) Financial impact parameterized as a reusable query pattern
-- -------------------------------------------------------------
-- Assumptions below are illustrative: 1,000 monthly orders, $25/hour labor.
WITH cycle AS (
    SELECT
        MAX(avg_cycle_time) FILTER (WHERE state = 'Before') AS before_cycle,
        MAX(avg_cycle_time) FILTER (WHERE state = 'After') AS after_cycle
    FROM state_kpis
),
assumptions AS (
    SELECT
        1000.0 AS monthly_order_volume,
        25.0 AS hourly_labor_cost
)
SELECT
    before_cycle - after_cycle AS minutes_saved_per_order,
    (before_cycle - after_cycle) / 60.0
        * monthly_order_volume AS monthly_hours_saved,
    (before_cycle - after_cycle) / 60.0
        * monthly_order_volume
        * hourly_labor_cost AS monthly_labor_capacity_value,
    (before_cycle - after_cycle) / 60.0
        * monthly_order_volume
        * hourly_labor_cost
        * 12.0 AS annual_labor_capacity_value
FROM cycle
CROSS JOIN assumptions;
