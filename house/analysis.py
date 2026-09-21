"""Analyze the cleaned SF Rent Board inventory.

Prints the stats tables and writes house/analysis_data.json for the write-up.

IMPORTANT CAVEAT, repeated in every output: monthly_rent is the rent a sitting
tenant is currently paying under rent control, not an asking rent. The sample is
dominated by long tenancies, so these figures describe the contract-rent
distribution of the existing stock. They are NOT a market-rate series and any
year-over-year movement here mostly reflects tenant turnover, not price changes.

Usage:
    .venv/bin/python house/analysis.py
"""

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE / "inventory_clean.parquet"
OUT = HERE / "analysis_data.json"

CAVEAT = (
    "Reported rents are contract rents of sitting tenants under rent control, "
    "not market asking rents."
)
# Below this many rows a neighborhood median is too noisy to show.
MIN_HOOD_N = 3000


def load():
    df = pd.read_parquet(SRC)
    # The rent questions are about tenancies, so owner-occupied, vacant and
    # non-residential rows are excluded from every rent figure below.
    tenant = df[(df.occupancy_type == "Occupied by non-owner")
                & (df.rent_status == "reported")].copy()
    return df, tenant


def rent_by_tenure(tenant):
    """The headline: median contract rent against years since move-in."""
    rows = []
    for bed in (0, 1, 2):
        sub = tenant[tenant.bedrooms_n == bed]
        g = sub.groupby("tenure_years", observed=True).rent_mid.agg(["median", "count"])
        g = g[(g.index <= 40) & (g["count"] >= 100)]
        rows.append({
            "bedrooms": bed,
            "label": {0: "Studio", 1: "1 bedroom", 2: "2 bedroom"}[bed],
            "points": [{"tenure": int(t), "median": float(r["median"]), "n": int(r["count"])}
                       for t, r in g.iterrows()],
        })
    return rows


def tenure_cohorts(tenant):
    """Tenure bands vs. the 0-2yr cohort, which is the closest thing here to
    a market rent (a recent move-in was priced at the market of its day)."""
    bands = [(0, 2, "0-2 yrs"), (3, 5, "3-5 yrs"), (6, 10, "6-10 yrs"),
             (11, 15, "11-15 yrs"), (16, 20, "16-20 yrs"), (21, 25, "21-25 yrs"),
             (26, 30, "26-30 yrs"), (31, 60, "31+ yrs")]
    base = None
    out = []
    for lo, hi, label in bands:
        sub = tenant[(tenant.tenure_years >= lo) & (tenant.tenure_years <= hi)]
        if len(sub) < 100:
            continue
        med = float(sub.rent_mid.median())
        if base is None:
            base = med
        out.append({
            "band": label, "median": med, "n": int(len(sub)),
            "pct_below_recent": round(100 * (med - base) / base, 1),
            "share_of_stock": round(100 * len(sub) / len(tenant.dropna(subset=["tenure_years"])), 1),
        })
    return out


def neighborhoods(df, tenant):
    """One row per neighborhood: rent, vacancy, stock age, SRO share."""
    tot = df.groupby("analysis_neighborhood", observed=True).size()
    vac = df[df.occupancy_type == "Vacant"].groupby(
        "analysis_neighborhood", observed=True).size()
    sro = df.groupby("analysis_neighborhood", observed=True).shared_bathroom.mean()
    built = df.groupby("analysis_neighborhood", observed=True).year_property_built.median()
    rent = tenant.groupby("analysis_neighborhood", observed=True).rent_mid.agg(["median", "count"])
    ten = tenant.groupby("analysis_neighborhood", observed=True).tenure_years.median()
    sqft = tenant.groupby("analysis_neighborhood", observed=True).sqft_mid.median()

    out = []
    for hood in tot.index:
        if rent.loc[hood, "count"] < MIN_HOOD_N if hood in rent.index else True:
            continue
        out.append({
            "neighborhood": hood,
            "n": int(tot[hood]),
            "median_rent": float(rent.loc[hood, "median"]),
            "rent_n": int(rent.loc[hood, "count"]),
            "vacancy_pct": round(100 * float(vac.get(hood, 0)) / int(tot[hood]), 2),
            "sro_pct": round(100 * float(sro[hood]), 1),
            "median_year_built": None if pd.isna(built[hood]) else int(built[hood]),
            "median_tenure": None if pd.isna(ten[hood]) else float(ten[hood]),
            "median_sqft": None if pd.isna(sqft[hood]) else float(sqft[hood]),
        })
    return sorted(out, key=lambda r: -r["median_rent"])


def bedroom_table(tenant):
    g = tenant.groupby("bedrooms_n", observed=True).rent_mid.agg(
        ["count", "median", "mean",
         lambda s: s.quantile(0.10), lambda s: s.quantile(0.90)])
    g.columns = ["n", "median", "mean", "p10", "p90"]
    return [{"bedrooms": int(b), "n": int(r["n"]),
             **{k: float(r[k]) for k in ("median", "mean", "p10", "p90")}}
            for b, r in g.iterrows() if b <= 5]


def vacancy_trend(df):
    """Vacancy by filing year. This one IS a real time series - occupancy_type is
    a point-in-time state, unlike rent, which is anchored to the move-in date."""
    out = []
    for yr, sub in df.groupby("submission_year", observed=True):
        out.append({"year": int(yr), "n": int(len(sub)),
                    "vacancy_pct": round(100 * float((sub.occupancy_type == "Vacant").mean()), 2)})
    return sorted(out, key=lambda r: r["year"])


def vacancy_by_building_size(df):
    buckets = pd.cut(df.unit_count, [0, 4, 10, 50, 100, 100000],
                     labels=["1-4", "5-10", "11-50", "51-100", "100+"])
    out = []
    for label, sub in df.groupby(buckets, observed=True):
        out.append({"size": str(label), "n": int(len(sub)),
                    "vacancy_pct": round(100 * float((sub.occupancy_type == "Vacant").mean()), 2)})
    return out


def utilities(df):
    return {c.replace("incl_", ""): round(100 * float(df[c].mean()), 1)
            for c in ("incl_water_sewer", "incl_refuse_recycling",
                      "incl_natural_gas", "incl_electricity")}


def quality(df):
    """The data-quality facts the write-up reports."""
    return {
        "rows": int(len(df)),
        "bedroom_unparsed": int(df.bedroom_count_raw.notna().sum() - df.bedrooms_n.notna().sum()),
        "bathroom_unparsed": 18,
        "rent_missing_pct": round(100 * float((df.rent_status == "missing").mean()), 2),
        "no_rent_paid": int((df.rent_status == "no_rent").sum()),
        "date_flags": int(df.date_flag.notna().sum()),
        "vacant_no_date": round(100 * float(
            df[df.occupancy_type == "Vacant"].vacancy_date.isna().mean()), 1),
        "history_json_pct": round(100 * float(df.occupancy_history_json.notna().mean()), 1),
        "sro_rows": int(df.shared_bathroom.sum()),
    }


def main():
    df, tenant = load()
    data = {
        "caveat": CAVEAT,
        "generated_from": SRC.name,
        "rows": int(len(df)),
        "tenant_rows": int(len(tenant)),
        "submission_years": sorted(int(y) for y in df.submission_year.dropna().unique()),
        "rent_by_tenure": rent_by_tenure(tenant),
        "tenure_cohorts": tenure_cohorts(tenant),
        "neighborhoods": neighborhoods(df, tenant),
        "bedroom_table": bedroom_table(tenant),
        "vacancy_trend": vacancy_trend(df),
        "vacancy_by_building_size": vacancy_by_building_size(df),
        "utilities": utilities(df),
        "quality": quality(df),
    }
    OUT.write_text(json.dumps(data, indent=1))

    print(f"!! {CAVEAT}\n")
    print(f"{len(df):,} rows | {len(tenant):,} tenant-occupied rows with a reported rent\n")

    print("== RENT BY TENURE COHORT (tenant-occupied)")
    print(f"{'band':<10}{'median':>9}{'vs 0-2yr':>10}{'n':>10}{'% stock':>9}")
    for r in data["tenure_cohorts"]:
        print(f"{r['band']:<10}${r['median']:>8,.0f}{r['pct_below_recent']:>9.1f}%"
              f"{r['n']:>10,}{r['share_of_stock']:>8.1f}%")

    print("\n== RENT BY BEDROOM COUNT")
    print(f"{'beds':<6}{'n':>9}{'p10':>9}{'median':>9}{'mean':>9}{'p90':>9}")
    for r in data["bedroom_table"]:
        print(f"{r['bedrooms']:<6}{r['n']:>9,}  ${r['p10']:>7,.0f}"
              f"${r['median']:>7,.0f}  ${r['mean']:>7,.0f}  ${r['p90']:>7,.0f}")

    print("\n== NEIGHBORHOODS (>=%d tenant rows), by median rent" % MIN_HOOD_N)
    print(f"{'neighborhood':<32}{'rent':>8}{'vac%':>7}{'SRO%':>7}{'tenure':>8}{'built':>7}{'sqft':>7}")
    for r in data["neighborhoods"]:
        print(f"{r['neighborhood']:<32}${r['median_rent']:>7,.0f}{r['vacancy_pct']:>7.1f}"
              f"{r['sro_pct']:>7.1f}{r['median_tenure']:>8.0f}{r['median_year_built']:>7}"
              f"{r['median_sqft']:>7,.0f}")

    print("\n== HIGHEST VACANCY")
    for r in sorted(data["neighborhoods"], key=lambda x: -x["vacancy_pct"])[:6]:
        print(f"  {r['neighborhood']:<32}{r['vacancy_pct']:>6.1f}%  "
              f"(SRO {r['sro_pct']:.0f}%, median rent ${r['median_rent']:,.0f})")

    print("\n== VACANCY BY FILING YEAR (a real time series, unlike rent)")
    for r in data["vacancy_trend"]:
        print(f"  {r['year']}  {r['vacancy_pct']:>5.1f}%   (n={r['n']:,})")

    print("\n== VACANCY BY BUILDING SIZE")
    for r in data["vacancy_by_building_size"]:
        print(f"  {r['size']:<8}{r['vacancy_pct']:>6.1f}%   (n={r['n']:,})")

    print("\n== UTILITIES INCLUDED IN BASE RENT")
    for k, v in data["utilities"].items():
        print(f"  {k:<20}{v:>6.1f}%")

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
