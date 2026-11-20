"""Shraddha's tab: where units are vacant, how vacancy changed, and how rent
differs by neighborhood.

Each chart runs a query from final/sql/shraddha_sql_analysis.sql (the query
number is in each chart's caption), with the dashboard filters added as
WHERE / HAVING conditions.

Before starting the app, run final/sql/shraddha_sql_analysis.sql once in
Workbench so the view v_shraddha_occupancy exists (chart 1 reads from it).
"""
from functools import lru_cache

import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

import theme
from db import in_clause, run_query

TAB_LABEL = "Shraddha: Occupancy & Vacancy"
YEARS = [2022, 2023, 2024, 2025, 2026]
DISTRICTS = list(range(1, 12))
BELOW = "#c8553d"   # neighborhoods below the citywide average rent
# 11 distinct colors, one per supervisor district (the default palette repeats after 10).
DISTRICT_COLORS = dict(zip(DISTRICTS, px.colors.qualitative.Safe))

# ---------------------------------------------------------------------------
# SQL (from shraddha_sql_analysis.sql, with the dashboard filters added)
# ---------------------------------------------------------------------------
# Chart 1 - Q6 view v_shraddha_occupancy (vacancy by neighborhood, as in Q5a/Q6).
# Split by filing year and cached, so changing a filter only re-adds numbers in
# pandas instead of re-running a 4-second query over 548k rows.
VACANCY_BY_NEIGHBORHOOD_YEAR = """
SELECT neighborhood,
       submission_year,
       COUNT(*)        AS residential_filings,
       SUM(is_vacant)  AS vacant_filings,
       SUM(est_rent)   AS rent_sum,
       COUNT(est_rent) AS rent_reports
FROM v_shraddha_occupancy
GROUP BY neighborhood, submission_year
"""

# Chart 2 - Q5b (window function LAG), unchanged. It has no filter values,
# so it runs once and is cached; the district filter is applied afterwards.
DISTRICT_VACANCY_BY_YEAR = """
WITH district_year AS (
    SELECT lp.district_id                                     AS district,
           r.submission_year,
           ROUND(100 * SUM(ot.name = 'Vacant') / COUNT(*), 2) AS vacancy_rate
    FROM UnitReport r
    JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
    JOIN LocationPoint lp ON lp.point_id          = r.point_id
    WHERE ot.name <> 'Non-Residential'
      AND lp.district_id IS NOT NULL
    GROUP BY lp.district_id, r.submission_year
)
SELECT district,
       submission_year,
       vacancy_rate,
       LAG(vacancy_rate) OVER w                          AS prev_year_rate,
       ROUND(vacancy_rate - LAG(vacancy_rate) OVER w, 2) AS change_pts
FROM district_year
WINDOW w AS (PARTITION BY district ORDER BY submission_year)
ORDER BY district, submission_year
"""

CITY_VACANCY_BY_YEAR = """
SELECT r.submission_year,
       ROUND(100 * SUM(ot.name = 'Vacant') / COUNT(*), 2) AS vacancy_rate
FROM UnitReport r
JOIN OccupancyType ot ON ot.occupancy_type_id = r.occupancy_type_id
WHERE ot.name <> 'Non-Residential'
GROUP BY r.submission_year
ORDER BY r.submission_year
"""

# Chart 3 - Q3 (two CTEs + 4-table join), with a filing-year filter in both CTEs.
RENT_VS_CITY = """
WITH neighborhood_rent AS (
    SELECT n.name                                 AS neighborhood,
           COUNT((rb.min_rent + rb.max_rent) / 2) AS rent_reports,
           AVG((rb.min_rent + rb.max_rent) / 2)   AS avg_rent
    FROM UnitReport r
    JOIN RentBand rb      ON rb.rent_band_id   = r.rent_band_id
    JOIN LocationPoint lp ON lp.point_id       = r.point_id
    JOIN Neighborhood n   ON n.neighborhood_id = lp.neighborhood_id
    WHERE r.submission_year IN ({years})
    GROUP BY n.name
    HAVING COUNT((rb.min_rent + rb.max_rent) / 2) >= 100
),
city AS (
    SELECT AVG((rb.min_rent + rb.max_rent) / 2) AS city_avg_rent
    FROM UnitReport r
    JOIN RentBand rb ON rb.rent_band_id = r.rent_band_id
    WHERE r.submission_year IN ({years})
)
SELECT nr.neighborhood,
       nr.rent_reports,
       ROUND(nr.avg_rent)                                                AS avg_rent,
       ROUND(c.city_avg_rent)                                            AS city_avg_rent,
       ROUND(nr.avg_rent - c.city_avg_rent)                              AS diff_from_city,
       ROUND(100 * (nr.avg_rent - c.city_avg_rent) / c.city_avg_rent, 1) AS pct_diff
FROM neighborhood_rent nr
CROSS JOIN city c
ORDER BY nr.avg_rent DESC
"""


def _years_label(years):
    return "all years" if len(years) == len(YEARS) else ", ".join(str(y) for y in years)


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _neighborhood_data():
    return run_query(VACANCY_BY_NEIGHBORHOOD_YEAR)


def vacancy_by_neighborhood_figure(years, min_filings):
    data = _neighborhood_data()
    data = data[data["submission_year"].isin(years)]
    city = 100 * data["vacant_filings"].sum() / data["residential_filings"].sum()
    df = (data.dropna(subset=["neighborhood"])
              .groupby("neighborhood", as_index=False)[["residential_filings", "vacant_filings",
                                                         "rent_sum", "rent_reports"]].sum())
    df = df[df["residential_filings"] >= min_filings]       # same as HAVING COUNT(*) >= n
    df["vacancy_rate"] = (100 * df["vacant_filings"] / df["residential_filings"]).round(2)
    df["avg_est_rent"] = (df["rent_sum"] / df["rent_reports"]).round(0)
    df = df.sort_values("vacancy_rate")                      # highest bar on top
    fig = go.Figure(go.Bar(
        x=df["vacancy_rate"], y=df["neighborhood"], orientation="h",
        marker_color=theme.BLUE,
        text=[f"{v:.1f}%" for v in df["vacancy_rate"]], textposition="outside",
        customdata=df[["residential_filings", "avg_est_rent"]],
        hovertemplate=("%{y}<br>Vacancy rate: %{x:.2f}%<br>%{customdata[0]:,} residential filings"
                       "<br>Avg rent ≈ $%{customdata[1]:,.0f}<extra></extra>"),
    ))
    fig.add_vline(x=city, line_dash="dash", line_color=theme.MUTED,
                  annotation_text=f"Citywide {city:.1f}%", annotation_position="top")
    fig.update_xaxes(title="% of residential filings that are vacant", ticksuffix="%",
                     range=[0, max(df["vacancy_rate"].max() * 1.15, city * 1.2, 1)])
    return theme.style(fig, f"Where are units vacant? ({_years_label(years)})",
                       height=max(320, 80 + 22 * len(df)))


@lru_cache(maxsize=1)
def _district_data():
    return run_query(DISTRICT_VACANCY_BY_YEAR), run_query(CITY_VACANCY_BY_YEAR)


def district_trend_figure(districts, metric):
    df, city = _district_data()
    df = df[df["district"].isin(districts)]
    column = "vacancy_rate" if metric == "rate" else "change_pts"
    fig = go.Figure()
    for d in districts:
        part = df[df["district"] == d].dropna(subset=[column])
        fig.add_scatter(
            x=part["submission_year"], y=part[column], mode="lines+markers", name=f"District {d}",
            line={"color": DISTRICT_COLORS[d]}, marker={"color": DISTRICT_COLORS[d]},
            customdata=part[["vacancy_rate", "change_pts"]],
            hovertemplate=(f"District {d}, " + "%{x}<br>Vacancy rate: %{customdata[0]:.2f}%"
                           "<br>Change from previous year: %{customdata[1]:+.2f} pts<extra></extra>"),
        )
    if metric == "rate":
        fig.add_scatter(x=city["submission_year"], y=city["vacancy_rate"], mode="lines",
                        name="Citywide", line={"color": theme.TEXT, "dash": "dash", "width": 3},
                        hovertemplate="Citywide, %{x}<br>Vacancy rate: %{y:.2f}%<extra></extra>")
        fig.update_yaxes(title="Vacancy rate", ticksuffix="%", rangemode="tozero")
        title = "Vacancy fell in every district, 2022-2026"
    else:
        fig.add_hline(y=0, line_color=theme.MUTED)
        fig.update_yaxes(title="Change from previous year (percentage points)")
        title = "Year-over-year change in vacancy rate"
    fig.update_xaxes(title="Filing year", dtick=1)
    fig.update_layout(legend={"orientation": "h", "y": -0.25})
    return theme.style(fig, title, height=460)


def rent_vs_city_figure(years, show):
    df = run_query(RENT_VS_CITY.format(years=in_clause(years)), years + years)
    city_avg = df["city_avg_rent"].iloc[0]
    if show == "top-bottom":
        df = df.sort_values("avg_rent")
        df = df.iloc[list(range(10)) + list(range(len(df) - 10, len(df)))] if len(df) > 20 else df
    df = df.sort_values("diff_from_city")                    # most expensive on top
    fig = go.Figure(go.Bar(
        x=df["diff_from_city"], y=df["neighborhood"], orientation="h",
        marker_color=[theme.BLUE if v >= 0 else BELOW for v in df["diff_from_city"]],
        text=[f"{p:+.0f}%" for p in df["pct_diff"]], textposition="outside",
        customdata=df[["avg_rent", "pct_diff", "rent_reports"]],
        hovertemplate=("%{y}<br>Avg rent ≈ $%{customdata[0]:,.0f}<br>%{x:+$,.0f} vs. city "
                       "(%{customdata[1]:+.1f}%)<br>%{customdata[2]:,} rent reports<extra></extra>"),
    ))
    spread = df["diff_from_city"].abs().max() * 1.25
    fig.update_xaxes(title=f"Difference from citywide average rent (${city_avg:,.0f})",
                     tickformat="$,.0f", range=[-spread, spread])
    return theme.style(fig, f"Neighborhood rent vs. citywide average ({_years_label(years)})",
                       height=max(320, 80 + 22 * len(df)))


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
            html.Label("Filing year (charts 1 and 3)", className="filter-label"),
            dcc.Dropdown(id="shraddha-years", options=[{"label": str(y), "value": y} for y in YEARS],
                         value=YEARS, multi=True, clearable=False),
        ], className="filter-row"),

        _card([
            html.Label("Minimum residential filings per neighborhood", className="filter-label"),
            dcc.Slider(id="shraddha-min-filings", min=0, max=5000, step=None, value=500,
                       marks={v: f"{v:,}" for v in [0, 100, 500, 1000, 2500, 5000]}),
            dcc.Loading(dcc.Graph(id="shraddha-vacancy")),
            _caption("Query Q6 (VIEW v_shraddha_occupancy), same measure as Q5a. Vacancy is concentrated "
                     "in a few areas: the Tenderloin, Chinatown and Lakeshore are well above the city "
                     "rate. Raise the slider to hide neighborhoods with too few filings to be reliable."),
        ]),

        _card([
            html.Label("Supervisor districts", className="filter-label"),
            dcc.Dropdown(id="shraddha-districts", multi=True, clearable=False, value=DISTRICTS,
                         options=[{"label": f"District {d}", "value": d} for d in DISTRICTS]),
            dcc.RadioItems(id="shraddha-metric", inline=True, value="rate",
                           options=[{"label": " Vacancy rate", "value": "rate"},
                                    {"label": " Change from previous year", "value": "change"}]),
            dcc.Loading(dcc.Graph(id="shraddha-trend")),
            _caption("Query Q5b (window function LAG). Vacancy fell in every district between 2022 and "
                     "2026. District 3 was highest every year; District 7 jumped in 2025 and fell 6.5 "
                     "points in 2026."),
        ]),

        _card([
            dcc.RadioItems(id="shraddha-show", inline=True, value="top-bottom",
                           options=[{"label": " Top 10 and bottom 10", "value": "top-bottom"},
                                    {"label": " All neighborhoods", "value": "all"}]),
            dcc.Loading(dcc.Graph(id="shraddha-rent")),
            _caption("Query Q3 (CTE + 4-table join). Rent is a $250 band, so each value is the average "
                     "band midpoint. Mission Bay is about 45% above the city average and Chinatown about "
                     "54% below it."),
        ]),
    ])


def register_callbacks(app):
    @app.callback(Output("shraddha-vacancy", "figure"),
                  Input("shraddha-years", "value"), Input("shraddha-min-filings", "value"))
    def _update_vacancy(years, min_filings):
        return vacancy_by_neighborhood_figure(sorted(years), min_filings)

    @app.callback(Output("shraddha-trend", "figure"),
                  Input("shraddha-districts", "value"), Input("shraddha-metric", "value"))
    def _update_trend(districts, metric):
        return district_trend_figure(sorted(districts or DISTRICTS), metric)

    @app.callback(Output("shraddha-rent", "figure"),
                  Input("shraddha-years", "value"), Input("shraddha-show", "value"))
    def _update_rent(years, show):
        return rent_vs_city_figure(sorted(years), show)
