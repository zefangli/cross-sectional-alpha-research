"""Stream a CRSP CSV into an auditable, year-partitioned daily panel."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "crsp" / "yb8xejbnpiflaprb.csv"
OUT = ROOT / "data" / "processed" / "crsp_daily_panel"
SUMMARY = ROOT / "data" / "processed" / "cleaning_validation.csv"


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
    valid = """
        TRY_CAST(DlyCalDt AS DATE) BETWEEN TRY_CAST(SecInfoStartDt AS DATE)
            AND TRY_CAST(SecInfoEndDt AS DATE)
    """
    universe = """
        USIncFlg = 'Y' AND SecurityType = 'EQTY' AND SecuritySubType = 'COM'
        AND ShareType = 'NS' AND PrimaryExch IN ('N', 'A', 'Q')
    """
    con.execute(f"CREATE VIEW raw AS SELECT * FROM {source}")
    con.execute(f"""
        COPY (
            SELECT DISTINCT
                TRY_CAST(PERMNO AS BIGINT) AS permno,
                TRY_CAST(DlyCalDt AS DATE) AS date,
                TRY_CAST(DlyRet AS DOUBLE) AS ret,
                TRY_CAST(DlyPrc AS DOUBLE) AS price,
                TRY_CAST(DlyVol AS BIGINT) AS volume,
                TRY_CAST(DlyCap AS DOUBLE) AS market_cap,
                SecInfoStartDt AS sec_info_start_date,
                SecInfoEndDt AS sec_info_end_date,
                PrimaryExch AS primary_exchange,
                USIncFlg AS us_incorporated_flag,
                SecurityType AS security_type,
                SecuritySubType AS security_subtype,
                ShareType AS share_type,
                TradingStatusFlg AS trading_status_flag,
                SecurityActiveFlg AS security_active_flag,
                DlyDelFlg AS delisting_flag,
                DlyRetMissFlg AS return_missing_flag,
                DlyRetDurFlg AS return_duration_flag,
                EXTRACT(YEAR FROM TRY_CAST(DlyCalDt AS DATE))::INTEGER AS year
            FROM raw
            WHERE {valid}
              AND {universe}
              AND TRY_CAST(DlyCalDt AS DATE) BETWEEN DATE '2005-01-01' AND DATE '2025-12-31'
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE TRUE)
    """)
    write_summary(con)
    print(f"Wrote panel: {OUT}")
    print(f"Wrote validation: {SUMMARY}")


if __name__ == '__main__':
    main()
