"""Andrei's dashboard tab.

The three charts below use Q1, Q3, and Q4 from
``final/sql/andrei_sql_analysis.sql``. The SQL is kept here as read-only
dashboard queries so that each visualization is tied to one project query.
"""
from functools import lru_cache

import plotly.graph_objects as go
from dash import Input, Output, dcc, html

import theme
from db import run_query


TAB_LABEL = "Andrei: Rent Bands & Housing Features"

# AI DISCLOSURE:
# I followed the dashboard structure provided by my teammate in keerat.py
# so that each member's tab uses the same organization and style. I copied
# the SQL logic from my own andrei_sql_analysis.sql into this file.

# I used Codex to help me understand how to connect SQL result tables to
# Plotly figures and Dash components. Codex helped suggest chart types,
# Plotly parameters, layout options, hover text, and callback structure.
# I also used AI assistance to understand the purpose of lru_cache and how
# it can prevent the dashboard from rerunning the same large SQL query for
# every display-control change.

# The AI-assisted portions of this file are the lru_cache functions and
# Plotly figure implementations. The SQL queries, business questions, and
# SQL logic are my own work and understanding, copied from my verified
# andrei_sql_analysis.sql file.

# I am reviewing and revising the dashboard code so that I understand how
# the SQL results are transformed into visualizations and how the caching
# behavior works. I will retain only code that I can explain and verify.


# ---------------------------------------------------------------------------
# SQL from andrei_sql_analysis.sql
# ---------------------------------------------------------------------------
# Q1: Count occupied and vacant residential reports within each valid rent band.
Q1_OCCUPANCY_BY_RENT = """
WITH occupancy_counts AS (
    SELECT
        rb.rent_band_id,
        rb.raw_label AS rent_band,
        COUNT(*) AS total_reports,
        SUM(CASE
                WHEN ot.name IN ('Occupied by non-owner', 'Occupied by owner')
                THEN 1 ELSE 0
            END) AS occupied_reports,
        SUM(CASE
                WHEN ot.name = 'Vacant' THEN 1 ELSE 0
            END) AS vacant_reports
    FROM UnitReport AS ur
    JOIN RentBand AS rb
        ON ur.rent_band_id = rb.rent_band_id
    JOIN OccupancyType AS ot
        ON ur.occupancy_type_id = ot.occupancy_type_id
    WHERE rb.min_rent IS NOT NULL
      AND ot.name <> 'Non-Residential'
    GROUP BY rb.rent_band_id, rb.raw_label
)
SELECT
    rent_band,
    total_reports,
    occupied_reports,
    vacant_reports,
    ROUND((100.0 * occupied_reports) / total_reports, 2) AS occupied_percent,
    ROUND((100.0 * vacant_reports) / total_reports, 2) AS vacant_percent
FROM occupancy_counts
ORDER BY rent_band;
"""


# Q3: Find the most frequently reported bedroom/bathroom/square-footage
# combination within each rent band.
Q3_ROOM_PROFILES = """
WITH report_combinations AS (
    SELECT
        rb.rent_band_id,
        rb.raw_label AS rent_band,
        bed.canonical_bedrooms,
        bath.canonical_bathrooms,
        sb.raw_label AS sqft_band,
        COUNT(ur.unique_id) AS report_combination_count
    FROM UnitReport AS ur
    JOIN RentBand AS rb
        ON ur.rent_band_id = rb.rent_band_id
    JOIN BedroomLabel AS bed
        ON ur.bedroom_label_id = bed.bedroom_label_id
    JOIN BathroomLabel AS bath
        ON ur.bathroom_label_id = bath.bathroom_label_id
    JOIN SquareFootageBand AS sb
        ON ur.sqft_band_id = sb.sqft_band_id
    WHERE rb.min_rent IS NOT NULL
      AND bed.canonical_bedrooms IS NOT NULL
      AND bath.canonical_bathrooms IS NOT NULL
      AND sb.min_sqft IS NOT NULL
    GROUP BY rb.rent_band_id, rb.raw_label,
        bed.canonical_bedrooms, bath.canonical_bathrooms,
        sb.raw_label
),
ranked_combinations AS (
    SELECT
        rc.rent_band_id,
        rc.rent_band,
        rc.canonical_bedrooms,
        rc.canonical_bathrooms,
        rc.sqft_band,
        rc.report_combination_count,
        RANK() OVER (
            PARTITION BY rc.rent_band_id
            ORDER BY rc.report_combination_count DESC
        ) AS combination_rank,
        SUM(rc.report_combination_count) OVER (
            PARTITION BY rc.rent_band_id
        ) AS rent_band_total
    FROM report_combinations AS rc
)
SELECT
    rent_band,
    canonical_bedrooms,
    canonical_bathrooms,
    sqft_band,
    report_combination_count,
    ROUND((100.0 * report_combination_count) / rent_band_total, 2)
        AS combination_percent
FROM ranked_combinations
WHERE combination_rank = 1
ORDER BY rent_band;
"""


# Q4: Calculate each rent band's yearly share, then compare it with the prior
# filing year using LAG().
Q4_RENT_BAND_SHARES = """
WITH yearly_counts AS (
    SELECT
        ur.submission_year,
        rb.rent_band_id,
        rb.raw_label AS rent_band,
        COUNT(ur.unique_id) AS report_count
    FROM UnitReport AS ur
    JOIN RentBand AS rb
        ON ur.rent_band_id = rb.rent_band_id
    WHERE rb.min_rent IS NOT NULL
    GROUP BY ur.submission_year, rb.rent_band_id, rb.raw_label
),
yearly_totals AS (
    SELECT
        yc.submission_year,
        SUM(yc.report_count) AS total_reports
    FROM yearly_counts AS yc
    GROUP BY yc.submission_year
),
yearly_shares AS (
    SELECT
        yc.submission_year,
        yc.rent_band_id,
        yc.rent_band,
        ROUND((100.0 * yc.report_count) / yt.total_reports, 2)
            AS share_percentage
    FROM yearly_counts AS yc
    JOIN yearly_totals AS yt
        ON yc.submission_year = yt.submission_year
)
SELECT
    ys.submission_year,
    ys.rent_band,
    ys.share_percentage,
    LAG(ys.share_percentage) OVER (
        PARTITION BY ys.rent_band_id
        ORDER BY ys.submission_year
    ) AS previous_year_share_percentage,
    ys.share_percentage - LAG(ys.share_percentage) OVER (
        PARTITION BY ys.rent_band_id
        ORDER BY ys.submission_year
    ) AS percentage_point_change
FROM yearly_shares AS ys
ORDER BY ys.rent_band, ys.submission_year;
"""


# Cache the database results while the dashboard is running. The controls
# below change the display, so they do not need to rerun the large queries.
@lru_cache(maxsize=1)
def _q1_data():
    return run_query(Q1_OCCUPANCY_BY_RENT)


@lru_cache(maxsize=1)
def _q3_data():
    return run_query(Q3_ROOM_PROFILES)


@lru_cache(maxsize=1)
def _q4_data():
    return run_query(Q4_RENT_BAND_SHARES)


# ---------------------------------------------------------------------------
# Plotly figures
# ---------------------------------------------------------------------------
def occupancy_figure(metric):
    """Show occupied and vacant reports for each rent band."""
    df = _q1_data().copy()
    value_suffix = "_percent" if metric == "percent" else "_reports"
    occupied_column = f"occupied{value_suffix}"
    vacant_column = f"vacant{value_suffix}"
    x_title = "Share of reports (%)" if metric == "percent" else "Number of reports"

    fig = go.Figure()
    fig.add_bar(
        name="Occupied",
        y=df["rent_band"],
        x=df[occupied_column],
        orientation="h",
        marker_color=theme.BLUE,
        hovertemplate=(
            "%{y}<br>Occupied: %{x:.2f}"
            + ("%" if metric == "percent" else " reports")
            + "<extra></extra>"
        ),
    )
    fig.add_bar(
        name="Vacant",
        y=df["rent_band"],
        x=df[vacant_column],
        orientation="h",
        marker_color=theme.GRAY,
        hovertemplate=(
            "%{y}<br>Vacant: %{x:.2f}"
            + ("%" if metric == "percent" else " reports")
            + "<extra></extra>"
        ),
    )
    fig.update_layout(barmode="group", showlegend=True)
    fig.update_xaxes(title=x_title)
    fig.update_yaxes(categoryorder="array", categoryarray=list(df["rent_band"]))
    return theme.style(fig, "Occupied and vacant reports by rent band", height=700)


def rent_share_figure(view_type):
    """Show each rent band's share of reports across filing years."""
    df = _q4_data().copy()
    pivot = df.pivot(index="rent_band", columns="submission_year", values="share_percentage")
    pivot = pivot.sort_index()
    years = list(pivot.columns)

    if view_type == "line":
        fig = go.Figure()
        for rent_band in pivot.index:
            fig.add_scatter(
                x=years,
                y=pivot.loc[rent_band].tolist(),
                mode="lines+markers",
                name=rent_band,
                hovertemplate=(
                    f"{rent_band}<br>Year: %{{x}}<br>Share: %{{y:.2f}}%"
                    "<extra></extra>"
                ),
            )
        fig.update_xaxes(title="Filing year", dtick=1)
        fig.update_yaxes(title="Share of that year's reports", ticksuffix="%")
        return theme.style(fig, "Rent-band share across filing years", height=650)

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=years,
        y=list(pivot.index),
        colorscale="Blues",
        zmin=0,
        zmax=100,
        colorbar={"title": "Share (%)"},
        hovertemplate="Rent band: %{y}<br>Year: %{x}<br>Share: %{z:.2f}%<extra></extra>",
    ))
    fig.update_xaxes(title="Filing year", dtick=1)
    fig.update_yaxes(title="Rent band")
    return theme.style(fig, "Rent-band share across filing years", height=700)


def room_profile_figure(view_type):
    """Show the most frequently reported room/size profile by rent band."""
    df = _q3_data().copy()
    df["profile"] = (
        df["canonical_bedrooms"].astype(str)
        + " bed / "
        + df["canonical_bathrooms"].astype(str)
        + " bath / "
        + df["sqft_band"]
    )

    if view_type == "percent":
        x_values = df["combination_percent"]
        x_title = "Share of reports within rent band (%)"
        text = [f"{value:.2f}%" for value in x_values]
        hover_value = "Share: %{x:.2f}%"
    else:
        x_values = df["report_combination_count"]
        x_title = "Number of reports"
        text = [f"{value:,}" for value in x_values]
        hover_value = "Reports: %{x:,}"

    fig = go.Figure(go.Bar(
        x=x_values,
        y=df["rent_band"],
        orientation="h",
        marker_color=theme.BLUE,
        text=text,
        textposition="outside",
        customdata=df[["profile", "report_combination_count", "combination_percent"]],
        hovertemplate=(
            "Rent band: %{y}<br>Profile: %{customdata[0]}<br>"
            + hover_value
            + "<br>Reports: %{customdata[1]:,}"
            + "<extra></extra>"
        ),
    ))
    fig.update_xaxes(title=x_title, ticksuffix="%" if view_type == "percent" else "")
    fig.update_yaxes(categoryorder="array", categoryarray=list(df["rent_band"]))
    return theme.style(fig, "Most common room and square-footage profile by rent band", height=700)


# ---------------------------------------------------------------------------
# Layout and callbacks
# ---------------------------------------------------------------------------
def _card(children):
    return html.Div(children, className="card")


def _caption(text):
    return html.P(text, className="caption")


def layout():
    return html.Div([
        _card([
            html.Label("Display", className="filter-label"),
            dcc.RadioItems(
                id="andrei-occupancy-metric",
                options=[
                    {"label": " Percent", "value": "percent"},
                    {"label": " Counts", "value": "counts"},
                ],
                value="percent",
                inline=True,
            ),
            dcc.Loading(dcc.Graph(id="andrei-occupancy")),
            _caption("Query Q1: residential occupancy composition by rent band."),
        ]),
        _card([
            html.Label("Display", className="filter-label"),
            dcc.RadioItems(
                id="andrei-room-profile-view",
                options=[
                    {"label": " Percent", "value": "percent"},
                    {"label": " Counts", "value": "counts"},
                ],
                value="percent",
                inline=True,
            ),
            dcc.Loading(dcc.Graph(id="andrei-room-profiles")),
            _caption("Query Q3: the most frequently reported bedroom, bathroom, and square-footage combination within each rent band."),
        ]),
        _card([
            html.Label("Chart type", className="filter-label"),
            dcc.RadioItems(
                id="andrei-rent-share-view",
                options=[
                    {"label": " Heatmap", "value": "heatmap"},
                    {"label": " Lines", "value": "line"},
                ],
                value="line",
                inline=True,
            ),
            dcc.Loading(dcc.Graph(id="andrei-rent-shares")),
            _caption("Query Q4: each rent band's share of reported inventory across filing years."),
        ]),
    ])


def register_callbacks(app):
    @app.callback(
        Output("andrei-occupancy", "figure"),
        Input("andrei-occupancy-metric", "value"),
    )
    def _update_occupancy(metric):
        return occupancy_figure(metric)

    @app.callback(
        Output("andrei-room-profiles", "figure"),
        Input("andrei-room-profile-view", "value"),
    )
    def _update_room_profiles(view_type):
        return room_profile_figure(view_type)

    @app.callback(
        Output("andrei-rent-shares", "figure"),
        Input("andrei-rent-share-view", "value"),
    )
    def _update_rent_shares(view_type):
        return rent_share_figure(view_type)
