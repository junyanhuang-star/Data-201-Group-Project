"""SF Rent Board Housing Inventory dashboard (DATA 201, Group 2).

Run from this folder:   python app.py   then open http://127.0.0.1:8050

Each group member owns one file in members/ and one tab in the app.
To add a member, import their module and add it to MEMBERS below.
"""
from dash import Dash, dcc, html

from members import andrei, keerat, shraddha

MEMBERS = [keerat, andrei, shraddha]

app = Dash(__name__, title="SF Rent Board Dashboard", suppress_callback_exceptions=True)

app.layout = html.Div([
    html.H1("SF Rent Board Housing Inventory"),
    html.P("551,551 owner filings, 2022-2026, queried live from MySQL (sf_rent_board).",
           className="subtitle"),
    dcc.Tabs([dcc.Tab(label=m.TAB_LABEL, children=m.layout()) for m in MEMBERS]),
], className="page")

for member in MEMBERS:
    member.register_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)
