"""Build the point-in-time eligible universe and 20-day total-return target."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "processed" / "crsp_daily_panel" / "**" / "*.parquet"
OUT = ROOT / "data" / "processed" / "research_panel"
SUMMARY = ROOT / "data" / "processed" / "research_panel_validation.csv"


def panel_query(source: str) -> str:
    return f"""
        WITH calendar AS (
            SELECT date, ROW_NUMBER() OVER (ORDER BY date) - 1 AS trading_day_index
            FROM (SELECT DISTINCT date FROM {source})
        ), history AS (
            SELECT base.*, calendar.trading_day_index,
                ABS(price) * volume AS dollar_volume,
                COUNT(*) OVER prior_20 AS prior_observation_count,
                COUNT(ABS(price) * volume) OVER prior_20 AS prior_dollar_volume_count,
                AVG(ABS(price) * volume) OVER prior_20 AS trailing_dollar_volume_20,
                COUNT(ret) OVER prior_history AS prior_valid_return_count,
                COUNT(ret) OVER forward_20 AS forward_return_count,
                MIN(ret) OVER forward_20 AS forward_min_return,
                PRODUCT(1 + ret) OVER forward_20 AS forward_return_product,
                LEAD(trading_day_index, 20) OVER next_20 AS forward_end_trading_day_index
            FROM {source} AS base
            JOIN calendar USING (date)
            WINDOW
                prior_20 AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING),
                prior_history AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
                forward_20 AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING),
                next_20 AS (PARTITION BY permno ORDER BY trading_day_index)
        )
        SELECT
            permno, date,
            CASE WHEN
                us_incorporated_flag = 'Y' AND security_type = 'EQTY'
                AND security_subtype = 'COM' AND share_type = 'NS'
                AND primary_exchange IN ('N', 'A', 'Q')
                AND issuer_type = 'CORP' AND conditional_type = 'RW'
                AND trading_status_flag = 'A'
                AND ABS(price) >= 5
                AND prior_observation_count = 20
                AND prior_dollar_volume_count = 20
                AND trailing_dollar_volume_20 >= 5000000
                AND prior_valid_return_count >= 252
            THEN TRUE ELSE FALSE END AS eligibility_flag,
            CASE WHEN forward_end_trading_day_index = trading_day_index + 20
                AND forward_return_count = 20 AND forward_min_return >= -1
                THEN forward_return_product - 1 END AS forward_return_20d,
            price, market_cap, volume, shares_outstanding,
            ret, return_ex_dividends, value_weighted_market_return,
            trailing_dollar_volume_20, prior_valid_return_count,
            delisting_flag, return_missing_flag, return_duration_flag,
            primary_exchange, issuer_type, conditional_type, trading_status_flag,
            EXTRACT(YEAR FROM date)::INTEGER AS year
        FROM history
    """


def build_panel(con, source: str):
    return con.sql(panel_query(source))


def main() -> None:
    try:
        import duckdb
    except ModuleNotFoundError:
        sys.exit("DuckDB is required. Run: python -m pip install -r requirements.txt")
    if not (ROOT / "data" / "processed" / "crsp_daily_panel").exists():
        sys.exit("Cleaned panel not found. Run src/data/clean_crsp.py first.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    source = f"parquet_scan('{SOURCE.as_posix()}')"
    con.execute(
        f"COPY ({panel_query(source)}) "
        f"TO '{OUT.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE TRUE)"
    )
    con.execute(f"""
        COPY (
            SELECT metric, value FROM (
                SELECT 'panel_rows' AS metric, COUNT(*)::VARCHAR AS value FROM parquet_scan('{OUT.as_posix()}/**/*.parquet')
                UNION ALL SELECT 'eligible_rows', COUNT(*)::VARCHAR FROM parquet_scan('{OUT.as_posix()}/**/*.parquet') WHERE eligibility_flag
                UNION ALL SELECT 'complete_20d_targets', COUNT(*)::VARCHAR FROM parquet_scan('{OUT.as_posix()}/**/*.parquet') WHERE forward_return_20d IS NOT NULL
                UNION ALL SELECT 'eligible_rows_with_target', COUNT(*)::VARCHAR FROM parquet_scan('{OUT.as_posix()}/**/*.parquet') WHERE eligibility_flag AND forward_return_20d IS NOT NULL
            )
        ) TO '{SUMMARY.as_posix()}' (HEADER, DELIMITER ',')
    """)
    print(f"Wrote research panel: {OUT}")


if __name__ == '__main__':
    main()
