-- Bayline fulfillment analysis
-- DuckDB dialect. Grain is one order in fact_orders and one step in fact_order_steps.
-- Same-day dock SLA is 120 minutes from wave drop to stage.

CREATE OR REPLACE VIEW order_enriched AS
SELECT
    o.order_id,
    o.facility_id,
    f.name AS facility_name,
    f.region,
    f.metro,
    f.labor_rate,
    o.period,
    o.pilot_flag,
    CAST(o.dropped_at AS TIMESTAMP) AS dropped_at,
    CAST(o.promised_at AS TIMESTAMP) AS promised_at,
    o.shift,
    o.channel,
    o.line_count,
    o.low_risk_flag,
    o.hazmat_flag,
    o.cycle_minutes,
    o.error_count,
    o.rework_flag,
    o.sla_miss_flag,
    DATE_TRUNC('week', CAST(o.dropped_at AS TIMESTAMP)) AS week_start,
    strftime(CAST(o.dropped_at AS TIMESTAMP), '%Y-%m-%d') AS order_date,
    CASE
        WHEN o.line_count = 1 THEN '1 line'
        WHEN o.line_count BETWEEN 2 AND 3 THEN '2-3 lines'
        WHEN o.line_count BETWEEN 4 AND 6 THEN '4-6 lines'
        ELSE '7+ lines'
    END AS line_band
FROM fact_orders o
JOIN dim_facility f USING (facility_id);

CREATE OR REPLACE VIEW step_enriched AS
SELECT
    s.order_id,
    s.step_id,
    s.step_name,
    s.step_seq,
    s.dwell_minutes,
    o.facility_id,
    o.facility_name,
    o.period,
    o.shift,
    o.line_band,
    o.cycle_minutes
FROM fact_order_steps s
JOIN order_enriched o USING (order_id);

-- 1. Period scorecard with distribution, not just averages
CREATE OR REPLACE TABLE kpi_period AS
SELECT
    period,
    COUNT(*) AS orders,
    ROUND(AVG(cycle_minutes), 1) AS mean_cycle,
    ROUND(MEDIAN(cycle_minutes), 1) AS median_cycle,
    ROUND(QUANTILE_CONT(cycle_minutes, 0.75), 1) AS p75_cycle,
    ROUND(QUANTILE_CONT(cycle_minutes, 0.90), 1) AS p90_cycle,
    ROUND(STDDEV(cycle_minutes), 1) AS sd_cycle,
    ROUND(100.0 * AVG(sla_miss_flag), 1) AS sla_miss_pct,
    ROUND(100.0 * AVG(CASE WHEN error_count > 0 THEN 1 ELSE 0 END), 1) AS error_rate_pct,
    ROUND(100.0 * AVG(rework_flag), 1) AS rework_rate_pct,
    ROUND(SUM(cycle_minutes) / 60.0, 1) AS labor_hours,
    ROUND(SUM(cycle_minutes) / 60.0 * AVG(labor_rate), 0) AS loaded_labor_usd
FROM order_enriched
GROUP BY period;

-- 2. Step bottleneck: share of dwell and change after the pilot
CREATE OR REPLACE TABLE step_profile AS
WITH step_period AS (
    SELECT
        period,
        step_id,
        step_name,
        step_seq,
        ROUND(AVG(dwell_minutes), 1) AS avg_dwell,
        ROUND(MEDIAN(dwell_minutes), 1) AS median_dwell,
        ROUND(QUANTILE_CONT(dwell_minutes, 0.90), 1) AS p90_dwell
    FROM step_enriched
    GROUP BY period, step_id, step_name, step_seq
),
totals AS (
    SELECT period, SUM(avg_dwell) AS total_avg
    FROM step_period
    GROUP BY period
)
SELECT
    b.step_seq,
    b.step_id,
    b.step_name,
    b.avg_dwell AS baseline_avg,
    p.avg_dwell AS pilot_avg,
    ROUND(b.avg_dwell - p.avg_dwell, 1) AS minutes_recovered,
    ROUND(100.0 * (b.avg_dwell - p.avg_dwell) / b.avg_dwell, 1) AS pct_recovered,
    ROUND(100.0 * b.avg_dwell / tb.total_avg, 1) AS baseline_share_pct,
    ROUND(100.0 * p.avg_dwell / tp.total_avg, 1) AS pilot_share_pct
FROM step_period b
JOIN step_period p
  ON b.step_id = p.step_id
 AND b.period = 'baseline'
 AND p.period = 'pilot'
JOIN totals tb ON tb.period = 'baseline'
JOIN totals tp ON tp.period = 'pilot'
ORDER BY b.step_seq;

-- 2b. Step profile by building, for the floor filter
CREATE OR REPLACE TABLE step_by_facility AS
SELECT
    facility_id,
    period,
    step_id,
    step_name,
    step_seq,
    ROUND(AVG(dwell_minutes), 1) AS avg_dwell,
    ROUND(MEDIAN(dwell_minutes), 1) AS median_dwell
FROM step_enriched
GROUP BY facility_id, period, step_id, step_name, step_seq
ORDER BY facility_id, period, step_seq;


-- 3. Facility x shift: where the pain actually lived
CREATE OR REPLACE TABLE facility_shift AS
SELECT
    facility_id,
    facility_name,
    shift,
    period,
    COUNT(*) AS orders,
    ROUND(MEDIAN(cycle_minutes), 1) AS median_cycle,
    ROUND(QUANTILE_CONT(cycle_minutes, 0.90), 1) AS p90_cycle,
    ROUND(100.0 * AVG(sla_miss_flag), 1) AS sla_miss_pct,
    ROUND(100.0 * AVG(rework_flag), 1) AS rework_pct
FROM order_enriched
GROUP BY facility_id, facility_name, shift, period
ORDER BY facility_id, shift, period;

-- 4. Heterogeneous effects: the redesign should not look uniform
CREATE OR REPLACE TABLE heterogeneity AS
SELECT
    cut,
    slice,
    baseline_n,
    pilot_n,
    baseline_median,
    pilot_median,
    ROUND(baseline_median - pilot_median, 1) AS recovered_minutes,
    ROUND(100.0 * (baseline_median - pilot_median) / NULLIF(baseline_median, 0), 1) AS recovered_pct
FROM (
    SELECT
        'shift' AS cut,
        shift AS slice,
        COUNT(*) FILTER (WHERE period = 'baseline') AS baseline_n,
        COUNT(*) FILTER (WHERE period = 'pilot') AS pilot_n,
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'baseline'), 1) AS baseline_median,
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'pilot'), 1) AS pilot_median
    FROM order_enriched
    GROUP BY shift
    UNION ALL
    SELECT
        'facility',
        facility_id,
        COUNT(*) FILTER (WHERE period = 'baseline'),
        COUNT(*) FILTER (WHERE period = 'pilot'),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'baseline'), 1),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'pilot'), 1)
    FROM order_enriched
    GROUP BY facility_id
    UNION ALL
    SELECT
        'line_band',
        line_band,
        COUNT(*) FILTER (WHERE period = 'baseline'),
        COUNT(*) FILTER (WHERE period = 'pilot'),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'baseline'), 1),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'pilot'), 1)
    FROM order_enriched
    GROUP BY line_band
    UNION ALL
    SELECT
        'channel',
        channel,
        COUNT(*) FILTER (WHERE period = 'baseline'),
        COUNT(*) FILTER (WHERE period = 'pilot'),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'baseline'), 1),
        ROUND(MEDIAN(cycle_minutes) FILTER (WHERE period = 'pilot'), 1)
    FROM order_enriched
    GROUP BY channel
);

-- 5. Weekly control chart
CREATE OR REPLACE TABLE weekly_trend AS
SELECT
    week_start,
    period,
    facility_id,
    COUNT(*) AS orders,
    ROUND(MEDIAN(cycle_minutes), 1) AS median_cycle,
    ROUND(QUANTILE_CONT(cycle_minutes, 0.90), 1) AS p90_cycle,
    ROUND(100.0 * AVG(sla_miss_flag), 1) AS sla_miss_pct
FROM order_enriched
GROUP BY week_start, period, facility_id
ORDER BY week_start, facility_id;

CREATE OR REPLACE TABLE weekly_network AS
SELECT
    week_start,
    period,
    COUNT(*) AS orders,
    ROUND(MEDIAN(cycle_minutes), 1) AS median_cycle,
    ROUND(QUANTILE_CONT(cycle_minutes, 0.90), 1) AS p90_cycle,
    ROUND(100.0 * AVG(sla_miss_flag), 1) AS sla_miss_pct,
    LAG(ROUND(MEDIAN(cycle_minutes), 1)) OVER (ORDER BY week_start) AS prior_median
FROM order_enriched
GROUP BY week_start, period
ORDER BY week_start;

-- 6. Within-facility rank of the worst cartons (window function interview staple)
CREATE OR REPLACE TABLE worst_cartons AS
SELECT *
FROM (
    SELECT
        order_id,
        facility_id,
        facility_name,
        period,
        shift,
        channel,
        line_count,
        cycle_minutes,
        sla_miss_flag,
        rework_flag,
        RANK() OVER (
            PARTITION BY facility_id, period
            ORDER BY cycle_minutes DESC
        ) AS cycle_rank
    FROM order_enriched
)
WHERE cycle_rank <= 8
ORDER BY period, facility_id, cycle_rank;

-- 7. Exception mix
CREATE OR REPLACE TABLE exception_mix AS
SELECT
    o.period,
    e.exception_code,
    e.exception_label,
    COUNT(*) AS events,
    ROUND(AVG(e.minutes_added), 1) AS avg_minutes_added,
    ROUND(100.0 * AVG(e.rework_flag), 1) AS rework_share_pct
FROM fact_exceptions e
JOIN order_enriched o USING (order_id)
WHERE e.exception_code <> 'missed_sla'
GROUP BY o.period, e.exception_code, e.exception_label
ORDER BY o.period, events DESC;

-- 8. Labor recovered at observed mix, then sensitivity on volume
CREATE OR REPLACE TABLE labor_bridge AS
WITH step_hours AS (
    SELECT
        o.period,
        o.facility_id,
        f.labor_rate,
        SUM(s.dwell_minutes) / 60.0 AS hours
    FROM fact_order_steps s
    JOIN fact_orders o USING (order_id)
    JOIN dim_facility f USING (facility_id)
    WHERE s.step_id IN ('slot_locate', 'pick', 'pack', 'qc')
    GROUP BY o.period, o.facility_id, f.labor_rate
)
SELECT
    facility_id,
    MAX(labor_rate) AS labor_rate,
    ROUND(SUM(hours) FILTER (WHERE period = 'baseline'), 1) AS baseline_hours,
    ROUND(SUM(hours) FILTER (WHERE period = 'pilot'), 1) AS pilot_hours,
    ROUND(
        SUM(hours) FILTER (WHERE period = 'baseline')
        - SUM(hours) FILTER (WHERE period = 'pilot'),
        1
    ) AS hours_recovered,
    ROUND(
        (
            SUM(hours) FILTER (WHERE period = 'baseline')
            - SUM(hours) FILTER (WHERE period = 'pilot')
        ) * MAX(labor_rate),
        0
    ) AS usd_recovered_in_window
FROM step_hours
GROUP BY facility_id;

-- 9. Same-day SLA waterfall: miss rate by the Fontana night cell vs network
CREATE OR REPLACE TABLE sla_cells AS
SELECT
    CASE
        WHEN facility_id = 'FNT-12' AND shift = 'Night' THEN 'Fontana night'
        ELSE 'Rest of network'
    END AS cell,
    period,
    COUNT(*) AS orders,
    ROUND(100.0 * AVG(sla_miss_flag), 1) AS sla_miss_pct,
    ROUND(MEDIAN(cycle_minutes), 1) AS median_cycle
FROM order_enriched
GROUP BY 1, 2
ORDER BY 1, 2;
