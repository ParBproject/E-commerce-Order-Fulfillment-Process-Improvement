# Data Dictionary & KPI Definitions

The repository contains two illustrative order-level datasets representing a process before and after a redesigned fulfillment workflow.

## Order-level fields

| Field | Type | Definition |
|---|---|---|
| `order_id` | string | Unique order identifier within each process state |
| `order_date` | date | Illustrative order-processing date |
| `validation_time` | numeric | Minutes spent validating the order |
| `validation_errors` | integer | Validation-stage error count |
| `inventory_time` | numeric | Minutes spent checking inventory |
| `stock_issues` | integer | Indicator/count of stock-related issues |
| `payment_time` | numeric | Minutes spent on payment processing |
| `payment_issues` | integer | Indicator/count of payment-stage issues |
| `picking_time` | numeric | Minutes spent picking and packing |
| `picking_errors` | integer | Picking/packing error count |
| `qc_time` | numeric | Minutes spent in quality control |
| `qc_rejects` | integer | Quality-control rejection count |
| `shipping_time` | numeric | Minutes spent in the shipping step |
| `total_cycle_time_minutes` | numeric | Total observed order cycle time |
| `total_errors` | integer | Total error count associated with the order |
| `rework_required` | binary | 1 if the order required rework, otherwise 0 |

The unified analytical layer adds:

| Field | Definition |
|---|---|
| `state` | `Before` or `After`, identifying the workflow version |

## Core KPI definitions

### Average cycle time

```text
mean(total_cycle_time_minutes)
```

Lower is preferred.

### Median cycle time

50th percentile of total cycle time. Less sensitive to extreme orders than the mean.

### P90 cycle time

90th percentile of total cycle time.

This highlights tail performance: 90% of orders have a cycle time at or below this value.

### Error rate

```text
orders with total_errors > 0 / total orders
```

This is order-level error incidence, not average number of errors per order.

### Rework rate

```text
orders with rework_required = 1 / total orders
```

### Orders per 8-hour day

```text
480 minutes / average cycle time
```

This is a simplified capacity indicator and assumes sequential processing with no parallelism or downtime.

### Monthly capacity

```text
orders per 8-hour day × 22 working days
```

This is a scenario metric rather than an observed production total.

## Improvement conventions

For metrics where **lower is preferred**:

```text
Improvement = (Before - After) / Before
```

For metrics where **higher is preferred**:

```text
Improvement = (After - Before) / Before
```

This avoids reporting a negative “improvement” when a desirable throughput metric increases.

## Pareto definitions

Process-step Pareto analysis uses the average time for each step.

```text
Step Share = Average Step Minutes / Sum of Average Step Minutes
```

Steps are ranked from highest to lowest average time, and cumulative share is calculated with a window function.

## Exception score

The dashboard uses an illustrative triage score:

```text
0.60 × cycle-time percentile
+ 0.25 × error indicator
+ 0.15 × rework indicator
```

The score is intended to prioritize orders for review. It is not a causal model, probability, or production risk score.

## Financial impact scenario

The labor-capacity scenario uses:

```text
Minutes Saved per Order
= Before Average Cycle Time - After Average Cycle Time

Monthly Hours Released
= Minutes Saved per Order / 60 × Monthly Order Volume

Monthly Capacity Value
= Monthly Hours Released × Hourly Labor Cost
```

The result represents modeled labor-capacity value under user-supplied assumptions. It should not be presented as guaranteed realized savings.

## Data-quality rules

The analytics layer checks for:

- missing required columns;
- missing order IDs;
- unparseable dates;
- duplicate order IDs;
- non-positive cycle times;
- invalid rework flags;
- missing numeric values.

## Interpretation boundary

The dataset is illustrative and designed to demonstrate an analytics workflow.

Before applying the same conclusions to a live business, the analysis would require controlled production data, process-definition consistency, sample-size review, confounder assessment, and monitoring after implementation.
