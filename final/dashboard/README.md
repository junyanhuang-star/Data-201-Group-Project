# Dashboard (Plotly Dash)

An interactive web app that runs our SQL queries live against the `sf_rent_board`
MySQL database. Each group member has one tab and owns one file in `members/`.

```
dashboard/
  app.py            the page: title + one tab per member (rarely needs edits)
  db.py             run_query(sql, params) -> pandas DataFrame
  theme.py          shared colors and chart style
  members/
    keerat.py       Keerat's tab (use as the example)
    andrei.py       Andrei's tab
    shraddha.py     Shraddha's tab
  assets/style.css  page styling (Dash loads it automatically)
  .env.example      template for your own MySQL login
```

## Run it (Windows, Anaconda Prompt)

1. Build the database first (see `final/docs/PIPELINE_RUN.md`), then run
   `final/sql/keerat_sql_analysis.sql` once in Workbench so the view
   `v_keerat_tenant_utilities` exists.
2. Install the packages (once):
   ```
   cd path\to\Data-201-Group-Project\final\dashboard
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to a new file named `.env` in the same folder and put your
   MySQL password in it. `.env` is in `.gitignore`, so it never goes to GitHub.
4. Start the app:
   ```
   python app.py
   ```
5. Open http://127.0.0.1:8050 in a browser. The first load takes about 15 seconds
   while the queries run; after that, filters respond in about a second.
   Stop the app with Ctrl+C.

## Adding your charts

Edit only your own file in `members/`, and follow `members/keerat.py`:

1. Put your SQL from `final/sql/<name>_sql_analysis.sql` in strings at the top.
   Use `%s` placeholders for filter values: `run_query(sql, [2024])`.
2. Write one function per chart that returns a Plotly figure and call
   `theme.style(fig, "Title")` so it matches the rest of the app.
3. `layout()` returns your filters and `dcc.Graph` components. Start every
   component id with your name (`andrei-...`) so ids never clash.
4. `register_callbacks(app)` connects each filter to its chart.

Work on your own branch and open a pull request to `main` when your tab works.
