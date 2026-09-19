# Fulfillment Operations Analytics Lab

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](requirements.txt)
[![SQL](https://img.shields.io/badge/SQL-DuckDB-FFF000?logo=duckdb&logoColor=111827)](sql/analytics_model.sql)
[![Dashboard](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](app.py)
[![Method](https://img.shields.io/badge/Method-DMAIC-0F766E)](#analytical-method)
[![CI](https://github.com/ParBproject/E-commerce-Order-Fulfillment-Process-Improvement/actions/workflows/ci.yml/badge.svg)](https://github.com/ParBproject/E-commerce-Order-Fulfillment-Process-Improvement/actions/workflows/ci.yml)

An employer-facing **Data Analyst / Operations Analyst** case study showing how raw order-level data can be turned into controlled KPIs, SQL analytical models, bottleneck prioritization, exception queues, trend monitoring, and decision-ready business impact.

The project combines **SQL + Python + dashboarding + data-quality controls + business communication** rather than presenting isolated charts.

## Executive results

The illustrative before/after scenario shows:

| Metric | Before | After | Reported change |
|---|---:|---:|---:|
| Average cycle time | 201.7 min | 75.6 min | **62.5% lower** |
| Daily throughput | 2.4 orders | 6.4 orders | **166.9% higher** |
| Error rate | 21.0% | 13.0% | **38.1% lower** |
| Rework rate | 11.0% | 6.0% | **45.5% lower** |
| Monthly capacity | 52 orders | 140 orders | **166.9% higher** |

These values are based on an illustrative process-improvement dataset and are presented as case-study evidence, not production claims.

## Employer snapshot

| Capability | Evidence |
|---|---|
| SQL | CTEs, reusable views, FILTER aggregates, window functions, PERCENT_RANK |
| Data modeling | Unified before/after analytical table and tidy process-step view |
| Data quality | Required-field, duplicate, date, range, and binary-flag checks |
| KPI design | Mean, median, P90, error incidence, rework, throughput, capacity |
| Root-cause analysis | Process-step comparison and Pareto bottleneck ranking |
| Trend analysis | Daily operational metrics and rolling 7-day cycle-time averages |
| Exception analytics | Percentile-based order prioritization |
| Business impact | Assumption-driven labor-capacity scenario |
| Visualization | Professional Streamlit dashboard and Plotly charts |
| Engineering | Reusable Python analytics, tests, DuckDB execution, CI on Python 3.10/3.12 |
| Documentation | Data dictionary and explicit KPI definitions |

## Analytical workflow

```text
Raw before / after order CSVs
        ↓
Data-quality validation
        ↓
Unified analytical dataset
        ↓
Reusable DuckDB SQL views
        ↓
KPI scorecard + process-step model
        ↓
Pareto bottleneck analysis
        ↓
Rolling operational trends
        ↓
Exception prioritization
        ↓
Business-impact assumptions
        ↓
Executive dashboard
```

## Professional dashboard

Run:

```bash
git clone https://github.com/ParBproject/E-commerce-Order-Fulfillment-Process-Improvement.git
cd E-commerce-Order-Fulfillment-Process-Improvement

python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

streamlit run app.py
```

The dashboard includes five workbenches:

**Executive Scorecard**  
Before/after KPIs, direction-aware improvement, and scenario-based capacity value.

**Bottlenecks & Pareto**  
Process-step comparisons and cumulative Pareto views for both workflow states.

**Trends & Exceptions**  
Rolling cycle-time monitoring plus an order-level exception queue.

**Data Quality**  
Duplicate, missing-value, invalid-cycle-time, and rework-flag controls.

**SQL Analytics Model**  
The full reproducible DuckDB model is visible directly in the dashboard.

## SQL analytical model

The main SQL model lives in **[sql/analytics_model.sql](sql/analytics_model.sql)**.

It reads the CSV files directly and creates reusable views rather than repeating logic in every chart.

### SQL techniques demonstrated

- common table expressions;
- conditional aggregation with `FILTER`;
- `MEDIAN` and `QUANTILE_CONT`;
- window `RANK`;
- `PERCENT_RANK`;
- cumulative window sums;
- rolling `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`;
- `LATERAL VALUES` to create a tidy process-step dataset;
- NULL-safe improvement calculations;
- reusable analytical views.

### Key views

| View | Purpose |
|---|---|
| `data_quality_report` | Source-data controls |
| `state_kpis` | Executive before/after scorecard |
| `kpi_improvement` | Direction-aware KPI change |
| `process_steps` | Tidy process-step fact view |
| `process_step_summary` | Before/after step performance |
| `bottleneck_pareto` | Ranked step contribution and cumulative share |
| `daily_operations` | Daily KPIs plus rolling cycle time |
| `order_exceptions` | Percentile-based review queue |

## Reproduce the SQL pipeline

```bash
python analytics/run_analysis.py
```

The runner builds the DuckDB model in memory and exports analytical tables to `outputs/`.

This turns the SQL from documentation into an executable data pipeline.

## Data-quality controls

A dashboard result should not be accepted before the input data is checked.

The Python and SQL layers explicitly surface:

- duplicate order IDs;
- required-field nulls;
- invalid dates;
- non-positive cycle times;
- invalid binary rework values.

See **[DATA_DICTIONARY.md](DATA_DICTIONARY.md)** for field definitions, KPI formulas, improvement conventions, and interpretation boundaries.

## Bottleneck and Pareto analysis

![Process step comparison](Visualizations/visualization_process_steps.png)

The process is transformed from wide step columns into a tidy step-level dataset.

Average time is then ranked by process step, and cumulative contribution is computed so the analysis can answer:

> Which few process stages account for the largest share of average processing time?

That is more decision-useful than reporting a list of averages without prioritization.

## Exception analysis

Orders are ranked for review using:

- cycle-time percentile;
- error incidence;
- rework status.

The dashboard uses an explicit heuristic score rather than hiding prioritization logic in manual review.

The score is a triage tool, not a causal model or probability.

## Operating trend

The analytical layer creates daily KPIs and a rolling 7-day average cycle time.

This provides a basic **control/monitoring** layer after the improvement, rather than ending the project at a one-time before/after comparison.

## Business-impact scenario

The sidebar lets a reviewer change:

- monthly order volume;
- hourly labor cost.

The model translates the observed average cycle-time difference into:

- minutes saved per order;
- monthly hours released;
- monthly labor-capacity value;
- annual labor-capacity value.

These are scenario values, not guaranteed accounting savings.

## Analytical method

The case study follows the DMAIC logic:

**Define** — identify slow fulfillment and operational friction.

**Measure** — establish cycle time, tail time, errors, rework, and capacity KPIs.

**Analyze** — use SQL and Python to rank bottlenecks, inspect exceptions, and identify process-step contribution.

**Improve** — compare the redesigned after-state process with the baseline.

**Control** — define repeatable KPI logic, rolling trends, data-quality checks, and exception monitoring.

## Existing visual evidence

### Business impact

![Business impact summary](Visualizations/visualization_business_impact.png)

### Cycle-time distribution

![Cycle time distribution](Visualizations/visualization_distribution.png)

### KPI comparison

![KPI comparison dashboard](Visualizations/visualization_comparison.png)

The current branch adds a new interactive dashboard and expanded analytical model; screenshots should be regenerated after deployment.

## Repository structure

```text
E-commerce-Order-Fulfillment-Process-Improvement/
├── app.py
├── before_state_data.csv
├── after_state_data.csv
├── SQL_Analysis_Queries.sql
├── src/
│   └── analytics.py
├── sql/
│   └── analytics_model.sql
├── analytics/
│   └── run_analysis.py
├── tests/
│   └── test_analytics.py
├── Visualizations/
├── .streamlit/config.toml
├── .github/workflows/ci.yml
├── DATA_DICTIONARY.md
├── requirements.txt
└── README.md
```

## Quality and reproducibility

GitHub Actions runs on Python **3.10 and 3.12** and verifies:

1. critical lint checks;
2. Python compilation;
3. KPI/analytics regression tests;
4. full DuckDB SQL-model execution;
5. exported analytical output files.

This means the SQL is continuously executed against the included source data instead of existing only as static text.

## Skills demonstrated

**SQL:** DuckDB, CTEs, conditional aggregation, window functions, percentile ranks, reusable analytical views.

**Data analysis:** pandas, NumPy, KPI design, distributions, Pareto analysis, rolling metrics, exception ranking.

**Business analytics:** capacity, process improvement, before/after analysis, scenario-based financial impact.

**Data quality:** validation rules, duplicate detection, field definitions, metric governance.

**Visualization:** Streamlit, Plotly, executive scorecards, bottleneck charts, monitoring views.

**Engineering:** modular Python, automated tests, CI/CD, reproducible SQL execution.

## Limitations

- The 200-order dataset is illustrative.
- The before/after samples are not a randomized controlled experiment.
- Process changes can be confounded by order mix, staffing, seasonality, or other operational differences.
- Capacity formulas simplify concurrency, downtime, and staffing constraints.
- Financial-impact outputs represent modeled capacity value, not guaranteed cash savings.
- A live deployment would require source-system lineage, access controls, refresh monitoring, and metric ownership.

## Responsible interpretation

This repository demonstrates a rigorous analytical workflow. Production decisions should use validated operational data and appropriate experimental or causal design where attribution is required.
