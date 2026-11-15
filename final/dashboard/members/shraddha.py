"""Shraddha's tab. Replace this placeholder with your charts.

Copy the structure of members/keerat.py:
  1. Put your SQL (from final/sql/shraddha_sql_analysis.sql) in strings at the top.
     Use %s placeholders for filter values and run it with run_query(sql, params).
  2. Write one function per chart that returns a Plotly figure.
     Call theme.style(fig, "Your title") so it matches the rest of the app.
  3. layout() returns your filters + dcc.Graph components.
     Start every component id with "shraddha-" so ids never clash with others.
  4. register_callbacks(app) connects each filter to its chart.
"""
from dash import html

TAB_LABEL = "Shraddha"


def layout():
    return html.Div(
        html.P("Shraddha's charts go here.", className="caption"),
        className="card",
    )


def register_callbacks(app):
    pass
