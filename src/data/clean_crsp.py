"""Stream a CRSP CSV into an auditable, year-partitioned daily panel.

The cleaned panel keeps every row of every US common share (`IDENTITY` below)
within its valid classification interval. Exchange, issuer, conditional-type
and trading-status screens are NOT applied here: they belong to *entry*
eligibility (`build_research_panel.py`), whereas this panel must also mark
names already held when they later halt, move exchange or delist. An earlier
version filtered on all of them, so a held name that changed status vanished
mid-hold and accrued 0 (2026-09-14 review, item 3). `SECURITY_AUDIT` still
reports the issuer/conditional/status mix for reference.

Delisting event rows are kept too. In CIZ format the delisting return is a
`DlyRet` observation with `DlyDelFlg = 'Y'`, dated the trading day after the
last trade and carrying placeholder classifications (`SecurityType = 'N/A'`,
`TradingStatusFlg = 'D'` ...) that fail every identity screen. They are
retained for any PERMNO that has identity rows in the panel, deduplicated to
one row per (PERMNO, date) with an identity row winning a tie, and are never
formation rows downstream (2026-09-15 follow-up, item 1).
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "crsp" / "yb8xejbnpiflaprb.csv"
OUT = ROOT / "data" / "processed" / "crsp_daily_panel"
SUMMARY = ROOT / "data" / "processed" / "cleaning_validation.csv"
SECURITY_AUDIT = ROOT / "data" / "processed" / "security_filter_audit.csv"


def write_summary(con) -> None:
    con.execute(f"CREATE VIEW clean AS SELECT * FROM parquet_scan('{OUT.as_posix()}/**/*.parquet')")
    con.execute(f"""
        COPY (
            SELECT metric, value FROM (
                SELECT 'panel_rows' AS metric, COUNT(*)::VARCHAR AS value FROM clean
                UNION ALL SELECT 'invalid_classification_dates_in_panel', COUNT(*)::VARCHAR FROM clean
                    WHERE date NOT BETWEEN TRY_CAST(sec_info_start_date AS DATE) AND TRY_CAST(sec_info_end_date AS DATE)
                UNION ALL SELECT 'missing_returns', COUNT(*)::VARCHAR FROM clean WHERE ret IS NULL
                UNION ALL SELECT 'zero_volume', COUNT(*)::VARCHAR FROM clean WHERE volume = 0
                UNION ALL SELECT 'duplicate_permno_date_groups', COUNT(*)::VARCHAR FROM (
                    SELECT permno, date FROM clean GROUP BY 1, 2 HAVING COUNT(*) > 1
                )
                UNION ALL SELECT 'rows_with_delisting_flag', COUNT(*)::VARCHAR FROM clean
                    WHERE COALESCE(delisting_flag, '') NOT IN ('', 'N')
                UNION ALL SELECT 'first_date', MIN(date)::VARCHAR FROM clean
                UNION ALL SELECT 'last_date', MAX(date)::VARCHAR FROM clean
                UNION ALL SELECT 'delisting_flag:' || COALESCE(delisting_flag, '<NULL>'), COUNT(*)::VARCHAR
                    FROM clean GROUP BY delisting_flag
            )
        ) TO '{SUMMARY.as_posix()}' (HEADER, DELIMITER ',')
    """)


VALID = """
        TRY_CAST(DlyCalDt AS DATE) BETWEEN TRY_CAST(SecInfoStartDt AS DATE)
            AND TRY_CAST(SecInfoEndDt AS DATE)
        AND TRY_CAST(DlyCalDt AS DATE) BETWEEN DATE '2005-01-01' AND DATE '2025-12-31'
"""
IDENTITY = """
        USIncFlg = 'Y' AND SecurityType = 'EQTY' AND SecuritySubType = 'COM'
        AND ShareType = 'NS'
"""
EVENT = "DlyDelFlg = 'Y'"


def clean_query(raw: str) -> str:
    """The cleaned panel as a SELECT over the raw relation `raw`: identity rows,
    plus delisting event rows for PERMNOs that have identity rows, one row per
    (PERMNO, date)."""
    return f"""
        SELECT * EXCLUDE (is_event) FROM (
            SELECT DISTINCT
                TRY_CAST(PERMNO AS BIGINT) AS permno,
                TRY_CAST(DlyCalDt AS DATE) AS date,
                TRY_CAST(DlyRet AS DOUBLE) AS ret,
                TRY_CAST(DlyPrc AS DOUBLE) AS price,
                TRY_CAST(DlyVol AS BIGINT) AS volume,
                TRY_CAST(DlyCap AS DOUBLE) AS market_cap,
                TRY_CAST(ShrOut AS DOUBLE) AS shares_outstanding,
                TRY_CAST(vwretd AS DOUBLE) AS value_weighted_market_return,
                TRY_CAST(DlyRetx AS DOUBLE) AS return_ex_dividends,
                SecInfoStartDt AS sec_info_start_date,
                SecInfoEndDt AS sec_info_end_date,
                PrimaryExch AS primary_exchange,
                USIncFlg AS us_incorporated_flag,
                SecurityType AS security_type,
                SecuritySubType AS security_subtype,
                ShareType AS share_type,
                IssuerType AS issuer_type,
                ConditionalType AS conditional_type,
                TradingStatusFlg AS trading_status_flag,
                SecurityActiveFlg AS security_active_flag,
                DlyDelFlg AS delisting_flag,
                DlyRetMissFlg AS return_missing_flag,
                DlyRetDurFlg AS return_duration_flag,
                EXTRACT(YEAR FROM TRY_CAST(DlyCalDt AS DATE))::INTEGER AS year,
                NOT ({IDENTITY}) AS is_event
            FROM {raw}
            WHERE {VALID}
              AND (({IDENTITY})
                   OR ({EVENT} AND PERMNO IN (
                          SELECT DISTINCT PERMNO FROM {raw} WHERE {VALID} AND {IDENTITY})))
        )
        QUALIFY ROW_NUMBER() OVER (PARTITION BY permno, date ORDER BY is_event) = 1
    """


def main() -> None:
    try:
        import duckdb
    except ModuleNotFoundError:
        sys.exit("DuckDB is required. Run: python -m pip install -r requirements.txt")
    if "--validate-only" in sys.argv:
        con = duckdb.connect()
        write_summary(con)
        print(f"Wrote validation: {SUMMARY}")
        return
    if not RAW.exists():
        sys.exit(f"Raw file not found: {RAW}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    source = f"read_csv('{RAW.as_posix()}', header=true, all_varchar=true)"
    con.execute(f"CREATE VIEW raw AS SELECT * FROM {source}")
    con.execute(f"""
        COPY (
            SELECT
                COALESCE(IssuerType, '<NULL>') AS issuer_type,
                COALESCE(ConditionalType, '<NULL>') AS conditional_type,
                COALESCE(TradingStatusFlg, '<NULL>') AS trading_status_flag,
                COUNT(*) AS rows
            FROM raw
            WHERE {VALID} AND {IDENTITY}
            GROUP BY 1, 2, 3
            ORDER BY rows DESC
        ) TO '{SECURITY_AUDIT.as_posix()}' (HEADER, DELIMITER ',')
    """)
    con.execute(f"""
        COPY ({clean_query('raw')})
        TO '{OUT.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE TRUE)
    """)
    write_summary(con)
    print(f"Wrote panel: {OUT}")
    print(f"Wrote validation: {SUMMARY}")


if __name__ == '__main__':
    main()
