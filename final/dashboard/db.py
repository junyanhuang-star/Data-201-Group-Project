"""Shared database helper for the dashboard.

Every chart gets its data by passing a SQL string to run_query(), so each
visual is tied directly to a query in final/sql/. Connection details come
from the .env file in this folder (see .env.example).
"""
import os
from pathlib import Path

import mysql.connector
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "sf_rent_board"),
    )


def run_query(sql, params=None):
    """Run one SELECT and return the result as a pandas DataFrame.

    Use %s placeholders in the SQL and pass the values in params, e.g.
    run_query("SELECT * FROM UnitReport WHERE submission_year = %s", [2024]).
    Never paste filter values into the SQL string yourself (SQL injection).
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=columns)
    # MySQL returns DECIMAL as Python Decimal; convert numeric-looking columns to float.
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() == df[col].notna().sum():
                df[col] = converted
    return df


def in_clause(values):
    """Placeholders for a WHERE ... IN (...) filter: in_clause([1, 2, 3]) -> '%s, %s, %s'."""
    return ", ".join(["%s"] * len(values))
