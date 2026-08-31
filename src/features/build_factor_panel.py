"""Build the aligned six-factor rank panel.

One pass over the research panel produces all six factors, then a single
`aligned` flag marks the rows on which every factor is simultaneously available
for an eligible stock. Cross-sectional percentile ranks are computed within date
**over the aligned rows only**, so all six ranks describe the same cross-section
and are directly comparable to each other.

Alignment deliberately does not require the forward target. The target is needed
for IC, but the portfolio work in Week 3 marks positions to daily returns and
would otherwise lose the last 20 trading days of every run.

Rows the portfolio may still hold -- a stock that stops being eligible while a
cohort is live -- stay in the research panel and are picked up from there at
backtest time; this file only defines where a *new* position may be opened.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.features.factors import ALL_FACTORS, factor_panel_query

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "processed" / "research_panel" / "**" / "*.parquet"
OUT = ROOT / "data" / "processed" / "factor_panel"
SUMMARY = ROOT / "data" / "processed" / "factor_panel_validation.csv"


def panel_query(source: str, names=None) -> str:
    names = names or ALL_FACTORS
    available = " AND ".join(f"f_{n} IS NOT NULL" for n in names)
    ranks = ",\n            ".join(
        f"CASE WHEN aligned THEN (RANK() OVER (PARTITION BY date ORDER BY f_{n}) - 1.0)"
        f" / NULLIF(COUNT(*) FILTER (aligned) OVER d - 1, 0) END AS rank_{n}"
        for n in names)
    return f"""
        WITH factors AS ({factor_panel_query(source, names)}),
        flagged AS (
            SELECT *, (eligibility_flag AND {available}) AS aligned FROM factors
        )
        SELECT permno, date, tdi, eligibility_flag, aligned, forward_return_20d,
            ret, value_weighted_market_return,
            {", ".join(f"f_{n}" for n in names)},
            {ranks},
            COUNT(*) FILTER (aligned) OVER d AS n_aligned,
            EXTRACT(YEAR FROM date)::INTEGER AS year
        FROM flagged
        WINDOW d AS (PARTITION BY date)
    """


def main() -> None:
    import duckdb

    if not (ROOT / "data" / "processed" / "research_panel").exists():
        sys.exit("Research panel not found. Run src/data/build_research_panel.py first.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    source = f"parquet_scan('{SOURCE.as_posix()}')"
    con.execute(
        f"COPY ({panel_query(source)}) TO '{OUT.as_posix()}' "
        f"(FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE TRUE)")
    scan = f"parquet_scan('{OUT.as_posix()}/**/*.parquet')"
    con.execute(f"""
        COPY (
            SELECT 'panel_rows' AS metric, COUNT(*)::VARCHAR AS value FROM {scan}
            UNION ALL SELECT 'eligible_rows', COUNT(*)::VARCHAR FROM {scan} WHERE eligibility_flag
            UNION ALL SELECT 'aligned_rows', COUNT(*)::VARCHAR FROM {scan} WHERE aligned
            UNION ALL SELECT 'aligned_share_of_eligible',
                (COUNT(*) FILTER (aligned) * 1.0 / COUNT(*) FILTER (eligibility_flag))::VARCHAR FROM {scan}
            UNION ALL SELECT 'aligned_with_target', COUNT(*)::VARCHAR FROM {scan}
                WHERE aligned AND forward_return_20d IS NOT NULL
            UNION ALL SELECT 'first_aligned_date', MIN(date)::VARCHAR FROM {scan} WHERE aligned
            UNION ALL SELECT 'last_aligned_date', MAX(date)::VARCHAR FROM {scan} WHERE aligned
            UNION ALL SELECT 'min_names_per_aligned_date', MIN(n_aligned)::VARCHAR FROM {scan} WHERE aligned
            UNION ALL SELECT 'mean_names_per_aligned_date',
                (SELECT AVG(n)::VARCHAR FROM (SELECT DISTINCT date, n_aligned AS n FROM {scan} WHERE aligned))
        ) TO '{SUMMARY.as_posix()}' (HEADER, DELIMITER ',')
    """)
    print(con.sql(f"SELECT * FROM read_csv('{SUMMARY.as_posix()}')").df().to_string())
    print(f"\nWrote factor panel: {OUT}")


if __name__ == "__main__":
    main()
