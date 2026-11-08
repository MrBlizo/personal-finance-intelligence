"""Plotly figures returned to the UI as JSON (rendered with plotly.js).

Figures use transparent backgrounds; the UI applies light/dark colours.
Measured data and model predictions are labelled distinctly.
"""
import json
from datetime import date

import pandas as pd
import plotly.graph_objects as go

ORANGE = "#E69F00"
SKYBLUE = "#56B4E9"
GREEN = "#009E73"
YELLOW = "#F0E442"
BLUE = "#0072B2"
VERM = "#D55E00"
PURPLE = "#CC79A7"
RED = "#BE1818"
GREY = "#8A8F98"
ASSET_LABELS = {"stock": "Stocks", "etf": "ETFs", "bond": "Bonds",
                "fund": "Funds", "crypto": "Crypto",
                "real_estate": "Real estate", "commodity": "Commodities",
                "cash": "Cash", "other": "Other"}
SERIES = [BLUE, ORANGE, GREEN, VERM, SKYBLUE, PURPLE, YELLOW, GREY]


def _layout(fig: go.Figure, currency: str | None = None,
            **kwargs) -> go.Figure:
    layout = {
        "template": "none", "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Segoe UI Variable Text, Segoe UI, Arial",
                 "size": 12},
        "margin": {"l": 56, "r": 16, "t": 16, "b": 40},
        "legend": {"orientation": "h", "y": -0.18, "x": 0},
        "hoverlabel": {"namelength": -1}}
    fig.update_layout(**{**layout, **kwargs})
    if currency:
        fig.update_yaxes(title_text=f"Amount / {currency}",
                         separatethousands=True)
    return fig


def to_json(fig: go.Figure) -> dict:
    """Return a figure as a plain JSON-serialisable dict."""
    return json.loads(fig.to_json())


def empty(message: str) -> dict:
    """Return a blank figure that shows ``message`` in the centre."""
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5,
                       xref="paper", yref="paper", font={"size": 14})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return to_json(_layout(fig))


def monthly_cashflow(df: pd.DataFrame, currency: str) -> dict:
    """Bars of monthly income and expenses with the net as a line."""
    data = df[df["amount_base"].notna()]
    if data.empty:
        return empty("No transactions in this period")
    month = data["txn_date"].dt.to_period("M").dt.to_timestamp()
    income = data[data["kind"] == "income"].groupby(
        month)["amount_base"].sum()
    spend = -data[data["kind"] == "expense"].groupby(
        month)["amount_base"].sum()
    idx = income.index.union(spend.index)
    income, spend = income.reindex(idx, fill_value=0), spend.reindex(
        idx, fill_value=0)
    fig = go.Figure([
        go.Bar(x=idx, y=income, name="Income", marker_color=GREEN,
               hovertemplate="%{y:,.2f}<extra>Income</extra>"),
        go.Bar(x=idx, y=spend, name="Expenses", marker_color=VERM,
               hovertemplate="%{y:,.2f}<extra>Expenses</extra>"),
        go.Scatter(x=idx, y=income - spend, name="Net", mode="lines+markers",
                   line={"color": BLUE, "width": 2},
                   hovertemplate="%{y:,.2f}<extra>Net</extra>"),
    ])
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    return to_json(_layout(fig, currency, barmode="group"))


def savings_rate(df: pd.DataFrame) -> dict:
    """Monthly savings rate = (income - expenses) / income."""
    data = df[df["amount_base"].notna()]
    month = data["txn_date"].dt.to_period("M").dt.to_timestamp()
    income = data[data["kind"] == "income"].groupby(
        month)["amount_base"].sum()
    spend = -data[data["kind"] == "expense"].groupby(
        month)["amount_base"].sum()
    rate = ((income - spend.reindex(income.index, fill_value=0))
            / income)[income > 0]
    if rate.empty:
        return empty("No income recorded in this period")
    fig = go.Figure(go.Scatter(
        x=rate.index, y=rate, mode="lines+markers", name="Savings rate",
        line={"color": GREEN, "width": 2},
        hovertemplate="%{y:.1%}<extra></extra>"))
    fig.add_hline(y=0, line={"color": GREY, "width": 1, "dash": "dot"})
    fig.update_yaxes(tickformat=".0%", title_text="Savings Rate / %")
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    return to_json(_layout(fig))


def category_breakdown(exp: pd.DataFrame, currency: str) -> dict:
    """Sunburst of spending by top-level and sub-category."""
    data = exp[exp["spend"] > 0]
    if data.empty:
        return empty("No expenses in this period")
    grouped = data.groupby(["top_category", "category"])["spend"].sum()
    ids, labels, parents, values = [], [], [], []
    for top, total in grouped.groupby(level=0).sum().items():
        ids.append(top)
        labels.append(top)
        parents.append("")
        values.append(total)
    for (top, cat), value in grouped.items():
        if cat == top:
            continue
        ids.append(f"{top}/{cat}")
        labels.append(cat)
        parents.append(top)
        values.append(value)
    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values,
        branchvalues="remainder", insidetextorientation="radial",
        marker={"colors": [SERIES[i % len(SERIES)] if not p else None
                           for i, p in enumerate(parents)]},
        hovertemplate=f"%{{label}}<br>%{{value:,.2f}} {currency}"
                      "<br>%{percentRoot:.1%} of total<extra></extra>"))
    return to_json(_layout(fig, margin={"l": 8, "r": 8, "t": 8, "b": 8}))


def category_trend(exp: pd.DataFrame, currency: str, top_n: int = 6
                   ) -> dict:
    """Stacked monthly spending for the largest categories."""
    data = exp[exp["spend"].notna()]
    if data.empty:
        return empty("No expenses in this period")
    totals = data.groupby("top_category")["spend"].sum().nlargest(top_n)
    data = data.assign(
        group=data["top_category"].where(
            data["top_category"].isin(totals.index), "Other"),
        month=data["txn_date"].dt.to_period("M").dt.to_timestamp())
    table = data.pivot_table(index="month", columns="group",
                             values="spend", aggfunc="sum", fill_value=0)
    order = [c for c in totals.index if c in table] + (
        ["Other"] if "Other" in table else [])
    fig = go.Figure([go.Bar(
        x=table.index, y=table[c], name=c,
        marker_color=SERIES[i % len(SERIES)],
        hovertemplate="%{y:,.2f}<extra>" + c + "</extra>")
        for i, c in enumerate(order)])
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    return to_json(_layout(fig, currency, barmode="stack"))


def weekday_heatmap(exp: pd.DataFrame, currency: str) -> dict:
    """Heatmap of total spending by weekday and month."""
    data = exp[exp["spend"] > 0]
    if data.empty:
        return empty("No expenses in this period")
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    data = data.assign(
        weekday=data["txn_date"].dt.day_of_week,
        month=data["txn_date"].dt.to_period("M").dt.to_timestamp())
    table = data.pivot_table(index="weekday", columns="month",
                             values="spend", aggfunc="sum",
                             fill_value=0).reindex(range(7), fill_value=0)
    fig = go.Figure(go.Heatmap(
        z=table.to_numpy(), x=table.columns, y=days,
        colorscale=[[0, "rgba(86,180,233,0.05)"], [1, BLUE]],
        colorbar={"title": {"text": currency}},
        hovertemplate="%{y} · %{x|%b %Y}<br>%{z:,.2f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    return to_json(_layout(fig))


def top_merchants(exp: pd.DataFrame, currency: str, n: int = 10) -> dict:
    """Horizontal bars of the payees with the highest total spending."""
    data = exp[exp["spend"] > 0]
    if data.empty:
        return empty("No expenses in this period")
    payee = data["merchant"].fillna("").where(
        data["merchant"].fillna("") != "", data["description"].str[:40])
    totals = data.groupby(payee)["spend"].agg(["sum", "count"]).nlargest(
        n, "sum").iloc[::-1]
    fig = go.Figure(go.Bar(
        x=totals["sum"], y=totals.index, orientation="h",
        marker_color=ORANGE, customdata=totals["count"],
        hovertemplate="%{y}<br>%{x:,.2f} in %{customdata} payments"
                      "<extra></extra>"))
    fig.update_xaxes(title_text=f"Amount / {currency}")
    return to_json(_layout(fig, margin={"l": 180, "r": 16, "t": 8,
                                        "b": 40}))


def budget_vs_actual(status: dict) -> dict:
    """Bars of spending per budget with the limit as a marker."""
    items = status["items"]
    if not items:
        return empty("No budgets defined yet")
    names = [i["category"] for i in items][::-1]
    spent = [i["spent"] for i in items][::-1]
    limits = [i["budget"] for i in items][::-1]
    colours = [{"over": RED, "at_risk": ORANGE, "ok": GREEN}[i["status"]]
               for i in items][::-1]
    fig = go.Figure([
        go.Bar(x=spent, y=names, orientation="h", name="Spent",
               marker_color=colours,
               hovertemplate="%{y}: %{x:,.2f}<extra>Spent</extra>"),
        go.Scatter(x=limits, y=names, mode="markers", name="Budget",
                   marker={"symbol": "line-ns-open", "size": 18,
                           "line": {"width": 3, "color": GREY}},
                   hovertemplate="%{y}: %{x:,.2f}<extra>Budget</extra>"),
    ])
    fig.update_xaxes(title_text=f"Amount / {status['currency']}")
    return to_json(_layout(fig, margin={"l": 140, "r": 16, "t": 32,
                                        "b": 48},
                           legend={"orientation": "h", "y": 1.02,
                                   "yanchor": "bottom", "x": 0}))


def net_worth_history(points: list[dict], currency: str) -> dict:
    """Monthly net worth split into liquid, investments and total."""
    if not points:
        return empty("Add accounts to see net worth over time")
    x = [p["date"] for p in points]
    fig = go.Figure([
        go.Scatter(x=x, y=[p["liquid"] for p in points], name="Liquid",
                   stackgroup="a", line={"color": SKYBLUE},
                   hovertemplate="%{y:,.2f}<extra>Liquid</extra>"),
        go.Scatter(x=x, y=[p["investments"] for p in points],
                   name="Investments", stackgroup="a",
                   line={"color": GREEN},
                   hovertemplate="%{y:,.2f}<extra>Investments</extra>"),
        go.Scatter(x=x, y=[p["total"] for p in points], name="Net worth",
                   mode="lines+markers", line={"color": BLUE, "width": 3},
                   hovertemplate="%{y:,.2f}<extra>Net worth</extra>"),
    ])
    fig.update_xaxes(tickformat="%b %Y")
    return to_json(_layout(fig, currency))


def allocation(holdings: list[dict], currency: str) -> dict:
    """Donut of portfolio market value by asset class."""
    data = pd.DataFrame([h for h in holdings
                         if h["market_value_base"]])
    if data.empty:
        return empty("Add holdings with prices to see allocation")
    by_class = data.groupby("asset_class")["market_value_base"].sum()
    fig = go.Figure(go.Pie(
        labels=[ASSET_LABELS.get(c, c) for c in by_class.index],
        values=by_class, hole=0.55, sort=True,
        marker={"colors": SERIES[:len(by_class)]},
        hovertemplate=f"%{{label}}<br>%{{value:,.2f}} {currency}"
                      "<br>%{percent}<extra></extra>"))
    return to_json(_layout(fig, margin={"l": 8, "r": 8, "t": 8, "b": 8}))


def forecast_fan(fc: dict) -> dict:
    """Fan chart of simulated balances (model prediction)."""
    x, cur = fc["dates"], fc["base_currency"]
    band = {"mode": "lines", "line": {"width": 0}, "hoverinfo": "skip"}
    fig = go.Figure([
        go.Scatter(x=x, y=fc["p95"], showlegend=False, **band),
        go.Scatter(x=x, y=fc["p5"], fill="tonexty", name="90% range",
                   fillcolor="rgba(0,114,178,0.15)", **band),
        go.Scatter(x=x, y=fc["p75"], showlegend=False, **band),
        go.Scatter(x=x, y=fc["p25"], fill="tonexty", name="50% range",
                   fillcolor="rgba(0,114,178,0.30)", **band),
        go.Scatter(x=x, y=fc["p50"], name="Median forecast",
                   line={"color": BLUE, "width": 2},
                   hovertemplate="%{x}<br>%{y:,.2f}<extra>Median</extra>"),
        go.Scatter(x=x, y=fc["scheduled_only"], name="Scheduled items only",
                   line={"color": ORANGE, "width": 1.5, "dash": "dash"},
                   hovertemplate="%{y:,.2f}<extra>Scheduled</extra>"),
    ])
    fig.add_hline(y=fc["threshold"], line={"color": RED, "width": 1,
                                           "dash": "dot"})
    fig.update_xaxes(tickformat="%d %b")
    return to_json(_layout(fig, cur))


def month_range(end: date, months: int) -> list[date]:
    """Return month-end dates for the ``months`` months ending at ``end``.

    The last element is ``end`` itself (today's snapshot).
    """
    stamps = pd.date_range(end=pd.Timestamp(end), periods=months,
                           freq="ME")
    out = [d.date() for d in stamps if d.date() < end]
    return out + [end]
