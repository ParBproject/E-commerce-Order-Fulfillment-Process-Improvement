"""Professional operational analytics dashboard for the fulfillment case study."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.analytics import (
    bottleneck_pareto,
    daily_operating_trend,
    data_quality_summary,
    financial_impact,
    improvement_table,
    load_order_states,
    process_step_summary,
    state_kpis,
    top_exception_orders,
)


ROOT = Path(__file__).resolve().parent
NAVY = "#0F172A"
TEAL = "#0F766E"
AMBER = "#D97706"
GRID = "#E2E8F0"


st.set_page_config(
    page_title="Fulfillment Analytics Lab",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background: #F8FAFC; }
    .block-container {
        max-width: 1450px;
        padding-top: 1.35rem;
        padding-bottom: 3rem;
    }
    .hero {
        padding: 2rem 2.2rem;
        border-radius: 22px;
        background:
            radial-gradient(circle at 88% 12%, rgba(56,189,248,.20), transparent 30%),
            linear-gradient(135deg, #0F172A 0%, #1E3A5F 58%, #0F766E 130%);
        color: white;
        box-shadow: 0 18px 48px rgba(15,23,42,.14);
        margin-bottom: 1.1rem;
    }
    .hero small {
        color: #99F6E4;
        text-transform: uppercase;
        letter-spacing: .15em;
        font-weight: 750;
    }
    .hero h1 {
        margin: .45rem 0 0;
        font-size: 2.25rem;
        letter-spacing: -.03em;
    }
    .hero p {
        margin: .75rem 0 0;
        max-width: 920px;
        color: #DCE7F4;
        line-height: 1.62;
    }
    .signal-card {
        padding: 1rem 1.05rem;
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 16px;
        min-height: 104px;
        box-shadow: 0 5px 18px rgba(15,23,42,.04);
    }
    .signal-label {
        color: #64748B;
        font-size: .75rem;
        text-transform: uppercase;
        letter-spacing: .09em;
        font-weight: 750;
    }
    .signal-value {
        color: #0F172A;
        font-size: 1.45rem;
        font-weight: 760;
        margin-top: .28rem;
    }
    .signal-note {
        color: #64748B;
        font-size: .79rem;
        margin-top: .18rem;
    }
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 15px;
        padding: .85rem 1rem;
        box-shadow: 0 4px 14px rgba(15,23,42,.035);
    }
    section[data-testid="stSidebar"] {
        background: #F1F5F9;
        border-right: 1px solid #E2E8F0;
    }
    .method-box {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 17px;
        padding: 1.05rem 1.2rem;
        line-height: 1.55;
        margin-bottom: .8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def signal_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="signal-card">
          <div class="signal-label">{label}</div>
          <div class="signal-value">{value}</div>
          <div class="signal-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data
def load_data() -> pd.DataFrame:
    return load_order_states(
        ROOT / "before_state_data.csv",
        ROOT / "after_state_data.csv",
    )


orders = load_data()
kpis = state_kpis(orders).set_index("State")
improvements = improvement_table(orders)
steps = process_step_summary(orders)
trend = daily_operating_trend(orders)

with st.sidebar:
    st.markdown("### Business assumptions")
    monthly_volume = st.number_input(
        "Monthly order volume",
        min_value=0,
        value=1000,
        step=100,
    )
    hourly_cost = st.number_input(
        "Hourly labor cost",
        min_value=0.0,
        value=25.0,
        step=1.0,
    )
    exception_state = st.selectbox("Exception review state", ["Before", "After"])
    exception_count = st.slider("Orders to review", 5, 25, 10, 5)

    st.divider()
    st.markdown("#### Dataset")
    st.write(f"**{len(orders):,}** total order records")
    st.write(
        f"**{int(kpis.loc['Before', 'Orders']):,}** before / "
        f"**{int(kpis.loc['After', 'Orders']):,}** after"
    )
    st.caption(
        "Illustrative process-improvement dataset. Business results should be "
        "validated with controlled production data before operational decisions."
    )


impact = financial_impact(
    orders,
    monthly_order_volume=int(monthly_volume),
    hourly_labor_cost=float(hourly_cost),
)

cycle_improvement = (
    1.0
    - kpis.loc["After", "Average Cycle Time"]
    / kpis.loc["Before", "Average Cycle Time"]
)
throughput_improvement = (
    kpis.loc["After", "Orders / 8h Day"]
    / kpis.loc["Before", "Orders / 8h Day"]
    - 1.0
)
error_improvement = (
    1.0
    - kpis.loc["After", "Error Rate"]
    / kpis.loc["Before", "Error Rate"]
)


st.markdown(
    """
    <div class="hero">
      <small>Operations & Data Analytics</small>
      <h1>Fulfillment Analytics Lab</h1>
      <p>
        A reproducible before/after operations case study combining SQL,
        KPI design, data-quality controls, process bottleneck analysis,
        Pareto prioritization, exception ranking, trend monitoring, and
        scenario-based financial impact.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    signal_card(
        "Cycle time",
        f"{cycle_improvement:.1%} lower",
        f"{kpis.loc['Before', 'Average Cycle Time']:.1f} → "
        f"{kpis.loc['After', 'Average Cycle Time']:.1f} min",
    )
with c2:
    signal_card(
        "Throughput",
        f"{throughput_improvement:.1%} higher",
        f"{kpis.loc['Before', 'Orders / 8h Day']:.1f} → "
        f"{kpis.loc['After', 'Orders / 8h Day']:.1f} orders/day",
    )
with c3:
    signal_card(
        "Error incidence",
        f"{error_improvement:.1%} lower",
        f"{kpis.loc['Before', 'Error Rate']:.1%} → "
        f"{kpis.loc['After', 'Error Rate']:.1%}",
    )
with c4:
    signal_card(
        "Annual capacity value",
        "$" + f"{impact['annual_cost_savings']:,.0f}",
        f"{monthly_volume:,} orders/mo @ " + "$" + f"{hourly_cost:,.0f}/hr",
    )

st.write("")

executive_tab, process_tab, trend_tab, quality_tab, sql_tab = st.tabs(
    [
        "Executive Scorecard",
        "Bottlenecks & Pareto",
        "Trends & Exceptions",
        "Data Quality",
        "SQL Analytics Model",
    ]
)


with executive_tab:
    st.markdown("### Before / after KPI scorecard")
    scorecard = kpis.reset_index()
    st.dataframe(
        scorecard.style.format(
            {
                "Average Cycle Time": "{:.1f}",
                "Median Cycle Time": "{:.1f}",
                "P90 Cycle Time": "{:.1f}",
                "Error Rate": "{:.1%}",
                "Rework Rate": "{:.1%}",
                "Orders / 8h Day": "{:.1f}",
                "Monthly Capacity": "{:.0f}",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("#### Direction-aware improvement")
    display_improvements = improvements.copy()
    display_improvements["Improvement"] = display_improvements["Improvement"].map(
        lambda value: "—" if pd.isna(value) else f"{value:.1%}"
    )
    st.dataframe(
        display_improvements,
        hide_index=True,
        use_container_width=True,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "Minutes saved / order",
        f"{impact['minutes_saved_per_order']:.1f}",
    )
    m2.metric(
        "Monthly hours released",
        f"{impact['monthly_hours_saved']:,.0f}",
    )
    m3.metric(
        "Monthly capacity value",
        "$" + f"{impact['monthly_cost_savings']:,.0f}",
    )
    m4.metric(
        "Annual capacity value",
        "$" + f"{impact['annual_cost_savings']:,.0f}",
    )

    st.info(
        "Financial impact is a scenario based on the sidebar assumptions. "
        "It represents labor-capacity value, not guaranteed accounting savings."
    )


with process_tab:
    st.markdown("### Where the process changed")

    pivot = (
        steps.pivot(
            index="Process Step",
            columns="State",
            values="Average Minutes",
        )
        .reset_index()
    )
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=pivot["Process Step"],
            y=pivot["Before"],
            name="Before",
            marker_color=NAVY,
        )
    )
    fig.add_trace(
        go.Bar(
            x=pivot["Process Step"],
            y=pivot["After"],
            name="After",
            marker_color=TEAL,
        )
    )
    fig.update_layout(
        title={"text": "Average Process-Step Time", "x": 0.02},
        barmode="group",
        height=430,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"color": NAVY},
        xaxis={"title": "", "gridcolor": GRID},
        yaxis={"title": "Minutes", "gridcolor": GRID},
        legend={"orientation": "h", "y": -0.18},
        margin={"l": 55, "r": 25, "t": 65, "b": 85},
    )
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)
    for column, state in [(left, "Before"), (right, "After")]:
        with column:
            pareto = bottleneck_pareto(orders, state)
            fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
            fig_pareto.add_trace(
                go.Bar(
                    x=pareto["Process Step"],
                    y=pareto["Average Minutes"],
                    name="Average minutes",
                    marker_color=TEAL if state == "After" else NAVY,
                ),
                secondary_y=False,
            )
            fig_pareto.add_trace(
                go.Scatter(
                    x=pareto["Process Step"],
                    y=pareto["Cumulative Share"],
                    name="Cumulative share",
                    line={"color": AMBER, "width": 2.5},
                    mode="lines+markers",
                ),
                secondary_y=True,
            )
            fig_pareto.update_layout(
                title={"text": f"{state} Bottleneck Pareto", "x": 0.02},
                height=410,
                paper_bgcolor="white",
                plot_bgcolor="white",
                showlegend=False,
                margin={"l": 45, "r": 35, "t": 65, "b": 100},
            )
            fig_pareto.update_yaxes(
                title_text="Average minutes",
                gridcolor=GRID,
                secondary_y=False,
            )
            fig_pareto.update_yaxes(
                title_text="Cumulative share",
                tickformat=".0%",
                range=[0, 1.05],
                secondary_y=True,
            )
            st.plotly_chart(fig_pareto, use_container_width=True)


with trend_tab:
    st.markdown("### Operating trend and exception review")

    trend_fig = go.Figure()
    palette = {"Before": NAVY, "After": TEAL}
    for state in ["Before", "After"]:
        subset = trend.loc[trend["state"] == state]
        trend_fig.add_trace(
            go.Scatter(
                x=subset["order_date"],
                y=subset["Cycle_Time_7D_Avg"],
                name=f"{state} 7-day average",
                line={"color": palette[state], "width": 2.6},
            )
        )
    trend_fig.update_layout(
        title={"text": "Rolling Average Cycle Time", "x": 0.02},
        height=420,
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis={"title": "", "gridcolor": GRID},
        yaxis={"title": "Minutes", "gridcolor": GRID},
        legend={"orientation": "h", "y": -0.16},
        margin={"l": 55, "r": 25, "t": 65, "b": 70},
    )
    st.plotly_chart(trend_fig, use_container_width=True)

    exceptions = top_exception_orders(
        orders,
        state=exception_state,
        limit=exception_count,
    )
    st.markdown(f"#### Highest-priority {exception_state.lower()} orders")
    st.dataframe(
        exceptions.style.format(
            {
                "total_cycle_time_minutes": "{:.1f}",
                "Cycle Percentile": "{:.1%}",
                "Exception Score": "{:.3f}",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        "Exception score combines cycle-time percentile, error incidence, and "
        "rework status for triage. It is a prioritization heuristic, not a causal score."
    )


with quality_tab:
    st.markdown("### Data-quality controls")
    q_rows = []
    for state, filename in [
        ("Before", ROOT / "before_state_data.csv"),
        ("After", ROOT / "after_state_data.csv"),
    ]:
        summary = data_quality_summary(pd.read_csv(filename))
        q_rows.append(
            {
                "State": state,
                "Rows": summary.rows,
                "Duplicate Order IDs": summary.duplicate_order_ids,
                "Missing Cells": summary.missing_cells,
                "Invalid Cycle Times": summary.invalid_cycle_times,
                "Invalid Rework Flags": summary.invalid_rework_flags,
            }
        )
    quality = pd.DataFrame(q_rows)
    st.dataframe(quality, hide_index=True, use_container_width=True)

    st.markdown(
        """
        <div class="method-box">
        <b>Why this matters</b><br><br>
        A dashboard is only as reliable as its input controls. The analytics layer
        checks required fields, date parsing, duplicate order IDs, non-positive
        cycle times, missing values, and binary rework flags before KPI reporting.
        </div>
        """,
        unsafe_allow_html=True,
    )


with sql_tab:
    st.markdown("### Reproducible DuckDB analytical model")
    st.markdown(
        """
        The SQL layer reads the source CSVs directly and builds reusable analytical
        views for data quality, KPI scorecards, process-step analysis, Pareto ranking,
        rolling trends, exception prioritization, and financial-impact scenarios.
        """
    )
    st.caption(
        "Techniques demonstrated: CTEs, FILTER aggregates, window functions, "
        "PERCENT_RANK, rolling frames, LATERAL VALUES, reusable views, and NULL-safe ratios."
    )

    sql_text = (ROOT / "sql" / "analytics_model.sql").read_text(encoding="utf-8")
    st.code(sql_text, language="sql", line_numbers=True)

st.caption(
    "Illustrative operations-analytics case study. Results demonstrate analytical "
    "methodology and should be validated with production data before decisions."
)
