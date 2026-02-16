# E-commerce Order Fulfillment Process Improvement

**How I turned a slow, error-prone order process into a fast, efficient machine using Lean Six Sigma**

Hey 👋

This project was born from a simple question: "Why does it take 3+ hours to fulfill an online order when it should take 1?"  
I analyzed a real-world e-commerce fulfillment workflow, applied classic Lean Six Sigma (DMAIC), fixed the biggest bottlenecks, and proved the impact with data from 200 orders (100 before + 100 after).

The result?  
- Cycle time down **62.5%** (from ~202 min to 76 min)  
- Throughput up **167%** (from 2.4 to 6.4 orders/day)  
- Errors down **38%**, rework down **45%**  
- **$36,000+ annual savings** with a 4-month payback

It’s the kind of project that makes operations managers smile and CFOs ask for more.

## The Story in Numbers

| Metric                  | Before      | After       | Improvement    |
|-------------------------|-------------|-------------|----------------|
| **Average Cycle Time**  | 201.7 min   | 75.6 min    | **-62.5%**     |
| **Daily Throughput**    | 2.4 orders  | 6.4 orders  | **+166.9%**    |
| **Error Rate**          | 21.0%       | 13.0%       | **-38.1%**     |
| **Rework Rate**         | 11.0%       | 6.0%        | **-45.5%**     |
| **Monthly Orders**      | 52          | 140         | **+166.9%**    |

**Bottom line**: Same team, same warehouse → **2.7x more orders processed**, way fewer mistakes, and real money saved.

## Visuals That Make the Point

These charts show the transformation better than any table.

### 1. Business Impact at a Glance

![Business Impact Summary](visualizations/visualization_business_impact.png)

The high-level wins: 62.5% faster, 167% more throughput, huge labor savings.

### 2. Process Step Times – Before vs After

![Process Steps Comparison](visualizations/visualization_process_steps.png)

The biggest wins were in picking (55 → 28 min) and eliminating the redundant QC step entirely.

### 3. Cycle Time Distribution

![Cycle Time Before vs After](visualizations/visualization_distribution.png)

Before: Wide spread, lots of 250+ min disasters.  
After: Tight cluster around 75 min. Much more predictable.

### 4. KPI Comparison Dashboard

![KPI Before vs After](visualizations/visualization_comparison.png)

Side-by-side bars that scream "this worked".

*(All images are in the `visualizations/` folder — drag them into issues if they don't load.)*

## Code Snippets I Actually Ran

Here are the most useful pieces of code from the analysis. They’re simple, readable, and show exactly how I pulled the insights.

### 1. Loading & Comparing the Data

```python
import pandas as pd

# Load both states
before = pd.read_csv("before_state_data.csv")
after = pd.read_csv("after_state_data.csv")

print("Before shape:", before.shape)
print("After shape:", after.shape)

# Key metrics
print("\nCycle Time:")
print(f"  Before: {before['total_cycle_time_minutes'].mean():.1f} min")
print(f"  After:  {after['total_cycle_time_minutes'].mean():.1f} min")
print(f"  Reduction: {((before['total_cycle_time_minutes'].mean() - after['total_cycle_time_minutes'].mean()) / before['total_cycle_time_minutes'].mean() * 100):.1f}%")

print("\nError & Rework Rates:")
print(f"  Error Rate Before: {before['total_errors'].mean() * 100:.1f}%")
print(f"  Error Rate After:  {after['total_errors'].mean() * 100:.1f}%")
print(f"  Rework Rate Before: {before['rework_required'].mean() * 100:.1f}%")
print(f"  Rework Rate After:  {after['rework_required'].mean() * 100:.1f}%")
