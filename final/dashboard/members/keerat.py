"""Keerat's tab: utilities included in base rent.

Each chart runs a query from final/sql/keerat_sql_analysis.sql (the query
number is in each chart's caption), with the dashboard filters added as
WHERE conditions.

To build your own tab, copy this file's structure:
  1. SQL strings at the top
  2. functions that run a query and return a Plotly figure
  3. layout()             -> what your tab shows
  4. register_callbacks() -> what happens when a filter changes
"""
from functools import lru_cache

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

import theme
from db import in_clause, run_query

TAB_LABEL = "Keerat: Utilities"
YEARS = [2022, 2023, 2024, 2025, 2026]
MAIN_UTILITIES = ["water_sewer", "refuse_recycling", "natural_gas", "electricity", "heat"]
UTILITY_LABELS = {
    "water_sewer": "Water & sewer", "refuse_recycling": "Trash & recycling",
    "natural_gas": "Natural gas", "electricity": "Electricity", "heat": "Heat",
}
# Fixed choices for the building-era filter. These SQL fragments are written
# here, never typed by the user, so they are safe to put into the query.
ERA_FILTERS = {
    "all": ("All buildings", ""),
    "pre1940": ("Built before 1940", "AND r.year_property_built < 1940"),
    "1940s-70s": ("Built 1940-1979", "AND r.year_property_built BETWEEN 1940 AND 1979"),
    "1980plus": ("Built 1980 or later", "AND r.year_property_built >= 1980"),
}

# ---------------------------------------------------------------------------
# SQL (from keerat_sql_analysis.sql, with a filing-year filter added)
# ---------------------------------------------------------------------------
# Q1, split by filing year. Both results are cached, so changing the year
# filter only re-adds numbers in pandas instead of re-running a 4-second query.
Q1_UTILITY_COUNTS_BY_YEAR = """
SELECT r.submission_year,
       u.name   AS utility,
       COUNT(*) AS tenant_reports_including_it
FROM ReportUtility ru
JOIN Utility u        ON u.utility_id = ru.utility_id
JOIN UnitReport r     ON r.unique_id = ru.unique_id
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.submission_year, u.utility_id, u.name
"""

Q1_TENANT_TOTALS_BY_YEAR = """
SELECT r.submission_year, COUNT(*) AS tenant_reports
FROM UnitReport r
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name = 'Occupied by non-owner'
GROUP BY r.submission_year
"""

Q3_RENT_BY_N_UTILITIES = """
WITH tenant_utilities AS (
    SELECT r.unique_id, r.rent_band_id, COUNT(ru.utility_id) AS n_utilities
    FROM UnitReport r
    JOIN OccupancyType ot      ON ot.occupancy_type_id = r.occupancy_type_id
    LEFT JOIN ReportUtility ru ON ru.unique_id = r.unique_id
    WHERE ot.name = 'Occupied by non-owner'
      AND r.submission_year IN ({years})
      {era_filter}
    GROUP BY r.unique_id, r.rent_band_id
)
SELECT tu.n_utilities,
       COUNT(*) AS tenant_reports,
       ROUND(AVG((rb.min_rent + rb.max_rent) / 2), 0) AS avg_rent_midpoint
FROM tenant_utilities tu
JOIN RentBand rb ON rb.rent_band_id = tu.rent_band_id
WHERE rb.min_rent IS NOT NULL
  AND rb.max_rent IS NOT NULL
GROUP BY tu.n_utilities
ORDER BY tu.n_utilities
"""

Q5_BY_BUILDING_ERA = """
SELECT building_era,
       COUNT(*)                              AS tenant_reports,
       ROUND(100 * AVG(has_water_sewer), 1)  AS water_sewer,
       ROUND(100 * AVG(has_refuse), 1)       AS refuse_recycling,
       ROUND(100 * AVG(has_gas), 1)          AS natural_gas,
       ROUND(100 * AVG(has_electricity), 1)  AS electricity,
       ROUND(100 * AVG(has_heat), 1)         AS heat
FROM v_keerat_tenant_utilities
GROUP BY building_era
ORDER BY building_era
"""


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _utility_counts():
    return run_query(Q1_UTILITY_COUNTS_BY_YEAR), run_query(Q1_TENANT_TOTALS_BY_YEAR)


def utility_share_figure(years, which):
    counts, totals = _utility_counts()
    counts = counts[counts["submission_year"].isin(years)]
    denominator = totals.loc[totals["submission_year"].isin(years), "tenant_reports"].sum()
    df = (counts.groupby("utility", as_index=False)["tenant_reports_including_it"].sum())
    df["pct_of_tenant_reports"] = (100 * df["tenant_reports_including_it"] / denominator).round(1)
    if which == "main":
        df = df[df["utility"].isin(MAIN_UTILITIES)]
    df = df.sort_values("pct_of_tenant_reports")          # largest bar on top
    labels = [UTILITY_LABELS.get(u, u.replace("_", " ").capitalize()) for u in df["utility"]]
    fig = go.Figure(go.Bar(
        x=df["pct_of_tenant_reports"], y=labels, orientation="h",
        marker_color=theme.BLUE,
        text=[f"{p:.1f}%" for p in df["pct_of_tenant_reports"]], textposition="outside",
        customdata=df["tenant_reports_including_it"],
        hovertemplate="%{y}<br>%{x:.1f}% of tenant reports<br>%{customdata:,} reports<extra></extra>",
    ))
    fig.update_xaxes(title="% of tenant reports that include it", ticksuffix="%",
                     range=[0, max(df["pct_of_tenant_reports"].max() * 1.15, 1)])
    return theme.style(fig, "Which utilities are included in tenants' rent?",
                       height=300 if which == "main" else 520)


def rent_by_n_utilities_figure(years, era_key):
    era_sql = ERA_FILTERS[era_key][1]
    df = run_query(Q3_RENT_BY_N_UTILITIES.format(years=in_clause(years), era_filter=era_sql), years)
    fig = go.Figure(go.Bar(
        x=df["n_utilities"].astype(str), y=df["avg_rent_midpoint"],
        marker_color=theme.BLUE,
        text=[f"${v:,.0f}" for v in df["avg_rent_midpoint"]], textposition="outside",
        customdata=df["tenant_reports"],
        hovertemplate="%{x} utilities included<br>Avg rent ≈ $%{y:,.0f}<br>%{customdata:,} tenant reports<extra></extra>",
    ))
    fig.update_xaxes(title="Number of utilities included in rent", type="category")
    fig.update_yaxes(title="Average rent (band midpoint)", tickprefix="$", tickformat=",",
                     range=[0, df["avg_rent_midpoint"].max() * 1.15])
    return theme.style(fig, f"More utilities included, lower rent ({ERA_FILTERS[era_key][0].lower()})")


@lru_cache(maxsize=1)
def _era_data():
    # The view has no filing-year column, so this chart uses all years and is cached.
    return run_query(Q5_BY_BUILDING_ERA)


def era_figure(selected_utilities):
    df = _era_data()
    df = df[~df["building_era"].str.contains("unknown")]
    eras = list(df["building_era"])
    fig = go.Figure()
    for era, color in zip(eras, theme.BLUE_SEQUENTIAL):
        row = df[df["building_era"] == era].iloc[0]
        values = [row[u] for u in selected_utilities]
        fig.add_bar(
            name=era.split(") ", 1)[-1].capitalize(),
            x=[UTILITY_LABELS[u] for u in selected_utilities], y=values,
            marker_color=color,
            hovertemplate="%{x}<br>" + era.split(") ", 1)[-1] + ": %{y:.1f}% of tenant reports<extra></extra>",
        )
    fig.update_layout(barmode="group", legend={"title": "Building built", "orientation": "h", "y": -0.2})
    fig.update_yaxes(title="% of tenant reports that include it", ticksuffix="%")
    return theme.style(fig, "Older buildings include utilities far more often", height=440)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
def _card(children):
    return html.Div(children, className="card")


def _caption(text):
    return html.P(text, className="caption")


def layout():
    return html.Div([
        html.Div([
            html.Label("Filing year", className="filter-label"),
            dcc.Dropdown(id="keerat-years", options=[{"label": str(y), "value": y} for y in YEARS],
                         value=YEARS, multi=True, clearable=False),
        ], className="filter-row"),

        _card([
            dcc.RadioItems(id="keerat-which", inline=True, value="main",
                           options=[{"label": " Main 5 utilities", "value": "main"},
                                    {"label": " All 16 utilities", "value": "all"}]),
            dcc.Loading(dcc.Graph(id="keerat-share")),
            _caption("Query Q1 (JOIN + GROUP BY). Water and trash are included for about 59% of tenants; "
                     "energy is usually the tenant's own bill."),
        ]),

        _card([
            html.Label("Building age", className="filter-label"),
            dcc.Dropdown(id="keerat-era", value="all", clearable=False,
                         options=[{"label": label, "value": key} for key, (label, _) in ERA_FILTERS.items()]),
            dcc.Loading(dcc.Graph(id="keerat-rent")),
            _caption("Query Q3 (CTE + LEFT JOIN). Rent is a $250 band, so each bar is the average band midpoint. "
                     "Try the building-age filter: the drop is partly explained by older, rent-controlled buildings."),
        ]),

        _card([
            dcc.Checklist(id="keerat-utilities", inline=True, value=MAIN_UTILITIES,
                          options=[{"label": f" {UTILITY_LABELS[u]}", "value": u} for u in MAIN_UTILITIES]),
            dcc.Loading(dcc.Graph(id="keerat-era-chart")),
            _caption("Query Q5 (VIEW v_keerat_tenant_utilities + CASE). All filing years. "
                     "Pre-1940 buildings include water and trash more than twice as often as post-1980 ones."),
        ]),
    ])


def register_callbacks(app):
    @app.callback(Output("keerat-share", "figure"),
                  Input("keerat-years", "value"), Input("keerat-which", "value"))
    def _update_share(years, which):
        return utility_share_figure(sorted(years), which)

    @app.callback(Output("keerat-rent", "figure"),
                  Input("keerat-years", "value"), Input("keerat-era", "value"))
    def _update_rent(years, era_key):
        return rent_by_n_utilities_figure(sorted(years), era_key)

    @app.callback(Output("keerat-era-chart", "figure"), Input("keerat-utilities", "value"))
    def _update_era(selected):
        selected = [u for u in MAIN_UTILITIES if u in (selected or [])] or MAIN_UTILITIES
        return era_figure(selected)
