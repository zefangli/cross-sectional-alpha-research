"""Build the point-in-time eligible universe and 20-day total-return target.

Eligibility at date t is decided entirely from information at the close of
t-1: the security passed every investability screen on its row at t-1 and
that row was the immediately preceding trading day. The target starts at the
close of t, so a book formed on eligible names is fully known before the close
it trades at. An earlier version screened on the same-day price and status
(2026-09-14 review, item 6), which made the cross-section depend on t's close.

Delisting event rows (`delisting_flag = 'Y'`, CRSP's CIZ convention: the
delisting return sits on a row dated the trading day after the last trade,
with placeholder classifications) are kept by the cleaner so a held name is
paid its delisting return. Such a row is never a formation row: the security
no longer exists to be bought, which is a fact about the row, not same-day
information about a tradable stock.

Two forward-return columns: `forward_return_20d` is the complete 20-day label
used for IC and model targets (NULL unless all 20 following trading days are
observed); `forward_return_20d_observed` compounds whatever is observed in the
next 20 trading days, delisting return included, for marking a position whose
window is cut short (2026-09-15 follow-up, item 2). It is NULL only when
nothing at all follows.
"""
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
                LEAD(trading_day_index, 20) OVER next_20 AS forward_end_trading_day_index,
                COUNT(ret) OVER forward_20_days AS observed_forward_count,
                PRODUCT(1 + ret) OVER forward_20_days AS observed_forward_product
            FROM {source} AS base
            JOIN calendar USING (date)
            WINDOW
                prior_20 AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING),
                prior_history AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING),
                forward_20 AS (PARTITION BY permno ORDER BY trading_day_index ROWS BETWEEN 1 FOLLOWING AND 20 FOLLOWING),
                forward_20_days AS (PARTITION BY permno ORDER BY trading_day_index RANGE BETWEEN 1 FOLLOWING AND 20 FOLLOWING),
                next_20 AS (PARTITION BY permno ORDER BY trading_day_index)
        ), screened AS (
            -- The investability screen evaluated on each row's own close ...
            SELECT *,
                us_incorporated_flag = 'Y' AND security_type = 'EQTY'
                AND security_subtype = 'COM' AND share_type = 'NS'
                AND primary_exchange IN ('N', 'A', 'Q')
                AND issuer_type = 'CORP' AND conditional_type = 'RW'
                AND trading_status_flag = 'A'
                AND ABS(price) >= 5
                AND prior_observation_count = 20
                AND prior_dollar_volume_count = 20
                AND trailing_dollar_volume_20 >= 5000000
                AND prior_valid_return_count >= 252 AS investable_at_close
            FROM history
        )
        SELECT
            permno, date,
            -- ... and applied one day later: eligible at t means investable at
            -- the close of t-1, where t-1 is this stock's previous trading day.
            -- A delisting event row is never a formation row.
            COALESCE(
                LAG(investable_at_close) OVER next_20
                AND LAG(trading_day_index) OVER next_20 = trading_day_index - 1
                AND COALESCE(delisting_flag, 'N') <> 'Y',
                FALSE) AS eligibility_flag,
            CASE WHEN forward_end_trading_day_index = trading_day_index + 20
                AND forward_return_count = 20 AND forward_min_return >= -1
                THEN forward_return_product - 1 END AS forward_return_20d,
            CASE WHEN observed_forward_count > 0
                THEN observed_forward_product - 1 END AS forward_return_20d_observed,
            price, market_cap, volume, shares_outstanding,
            ret, return_ex_dividends, value_weighted_market_return,
            trailing_dollar_volume_20, prior_valid_return_count,
            delisting_flag, return_missing_flag, return_duration_flag,
            primary_exchange, issuer_type, conditional_type, trading_status_flag,
            EXTRACT(YEAR FROM date)::INTEGER AS year
        FROM screened
        WINDOW next_20 AS (PARTITION BY permno ORDER BY trading_day_index)
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
                UNION ALL SELECT 'delisting_event_rows', COUNT(*)::VARCHAR FROM parquet_scan('{OUT.as_posix()}/**/*.parquet') WHERE COALESCE(delisting_flag, 'N') = 'Y'
                UNION ALL SELECT 'delisting_event_rows_eligible', COUNT(*)::VARCHAR FROM parquet_scan('{OUT.as_posix()}/**/*.parquet') WHERE COALESCE(delisting_flag, 'N') = 'Y' AND eligibility_flag
            )
        ) TO '{SUMMARY.as_posix()}' (HEADER, DELIMITER ',')
    """)
    print(f"Wrote research panel: {OUT}")


if __name__ == '__main__':
    main()
