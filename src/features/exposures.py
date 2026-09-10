"""Week 5 risk exposures: sector, rolling market beta, log market cap.

All three are determined by the close of *t*-1, the same rule every factor in
`factors.py` obeys: the point-in-time sector lookup uses the trading calendar's
*previous* date, beta's window ends at 1 PRECEDING (not `factors.py`'s
21 PRECEDING, which leaves room for the residual-momentum window above it), and
market cap is read one row back with the same `LAG(tdi) = tdi - 1` gap guard
`factors.py` uses for its own lagged scalars.

Sector comes from `SICCD`, which is point-in-time via the `SecInfoStartDt` /
`SecInfoEndDt` interval records -- the same mechanism the Week 1 universe screen
locked. Two traps in that interval history:

  - `SecurityHdrFlg='Y'` marks a record row, not "the current value" -- for a
    PERMNO whose code changed it lands on the FIRST interval more often than the
    last. It is never referenced below; the interval containing the date is
    joined directly.
  - About 1 in 10 interval rows carry a sentinel `SICCD` of `0`, `9999` or blank,
    clustered on end-of-life stubs. These are forward-filled from the prior
    interval **in start-date order**, so a sentinel can only inherit a code that
    was already known -- never one from an interval that starts later.

Sector granularity is fixed in advance at the ~11 SIC divisions in
`SIC_DIVISION_CASE` rather than the 81 two-digit SIC groups, which would run
roughly 20 names per bucket against a ~1,660-name cross-section -- too thin for
stable residualisation.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "crsp" / "yb8xejbnpiflaprb.csv"
PANEL_SOURCE = ROOT / "data" / "processed" / "crsp_daily_panel" / "**" / "*.parquet"
FACTOR_PANEL = ROOT / "data" / "processed" / "factor_panel" / "**" / "*.parquet"
OUT = ROOT / "data" / "processed" / "exposures"
SUMMARY = ROOT / "data" / "processed" / "exposures_validation.csv"

# Exposures are built over the full available panel history: they are inputs,
# not evaluation results. Research use of them downstream must still stop here.
LAST_RESEARCH_DATE = "2023-11-30"

SENTINEL_SICCD = "('0', '9999', '')"

# Standard SIC divisions (~11 groups against 81 two-digit groups). Declared
# once, in advance, so sector membership cannot be tuned to the data.
SIC_DIVISION_CASE = """
    CASE
        WHEN siccd BETWEEN 100 AND 999 THEN 1    -- agriculture, forestry, fishing
        WHEN siccd BETWEEN 1000 AND 1499 THEN 2  -- mining
        WHEN siccd BETWEEN 1500 AND 1799 THEN 3  -- construction
        WHEN siccd BETWEEN 2000 AND 3999 THEN 4  -- manufacturing
        WHEN siccd BETWEEN 4000 AND 4999 THEN 5  -- transportation, utilities
        WHEN siccd BETWEEN 5000 AND 5199 THEN 6  -- wholesale trade
        WHEN siccd BETWEEN 5200 AND 5999 THEN 7  -- retail trade
        WHEN siccd BETWEEN 6000 AND 6799 THEN 8  -- finance, insurance, real estate
        WHEN siccd BETWEEN 7000 AND 8999 THEN 9  -- services
        WHEN siccd BETWEEN 9100 AND 9729 THEN 10 -- public administration
        ELSE 0                                   -- unknown / nonclassifiable
    END
"""

# 252-day market-model window ending at t-1, so beta_252 is known at the close
# of t-1 like every other exposure and factor here.
W_BETA_T1 = "PARTITION BY lagged.permno ORDER BY lagged.tdi ROWS BETWEEN 252 PRECEDING AND 1 PRECEDING"


def sic_interval_query(raw_source: str) -> str:
    """One row per PERMNO/interval with a point-in-time, sentinel-free sector.

    `raw_source` is a relation with the raw export's own column names
    (`PERMNO`, `SecInfoStartDt`, `SecInfoEndDt`, `SICCD`). `SecurityHdrFlg` is
    deliberately never read.
    """
    return f"""
        WITH raw_intervals AS (
            SELECT DISTINCT
                TRY_CAST(PERMNO AS BIGINT) AS permno,
                TRY_CAST(SecInfoStartDt AS DATE) AS start_date,
                TRY_CAST(SecInfoEndDt AS DATE) AS end_date,
                CASE WHEN SICCD IS NULL OR SICCD IN {SENTINEL_SICCD} THEN NULL
                     ELSE TRY_CAST(SICCD AS INTEGER) END AS siccd_clean
            FROM {raw_source}
        ), filled AS (
            SELECT permno, start_date, end_date, siccd_clean,
                   siccd_clean IS NULL AS was_sentinel,
                   LAST_VALUE(siccd_clean IGNORE NULLS) OVER (
                       PARTITION BY permno ORDER BY start_date
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                   ) AS siccd
            FROM raw_intervals
        )
        SELECT permno, start_date, end_date,
               (was_sentinel AND siccd IS NOT NULL) AS carried_forward,
               {SIC_DIVISION_CASE} AS sector
        FROM filled
    """


def exposures_query(panel_source: str, sic_source: str) -> str:
    """Sector, beta_252 and log_mcap keyed by (permno, date, tdi).

    `panel_source` needs `permno, date, market_cap, ret,
    value_weighted_market_return`; `tdi` is (re)computed here from its own
    distinct dates so it matches the trading-day index `factors.py` builds the
    same way, and the two line up 1:1 when both are sourced from the same
    underlying panel.
    """
    return f"""
        WITH calendar AS (
            SELECT date, tdi, LAG(date) OVER (ORDER BY tdi) AS prev_date
            FROM (SELECT date, ROW_NUMBER() OVER (ORDER BY date) - 1 AS tdi
                  FROM (SELECT DISTINCT date FROM {panel_source}))
        ), base AS (
            SELECT p.permno, p.date, calendar.tdi, calendar.prev_date,
                   p.market_cap, p.ret, p.value_weighted_market_return
            FROM {panel_source} p JOIN calendar USING (date)
        ), lagged AS (
            -- Yesterday's market cap, but only when yesterday really is t-1 for
            -- this stock, matching the `turnover_lag1` / `cum_lag1` idiom in
            -- factors.py.
            SELECT *,
                   CASE WHEN LAG(tdi) OVER w = tdi - 1
                        THEN LAG(market_cap) OVER w END AS market_cap_lag1
            FROM base
            WINDOW w AS (PARTITION BY permno ORDER BY tdi)
        )
        SELECT lagged.permno, lagged.date, lagged.tdi,
               sic.sector,
               COALESCE(sic.carried_forward, FALSE) AS sector_carried_forward,
               CASE WHEN market_cap_lag1 > 0 THEN LN(market_cap_lag1) END AS log_mcap,
               CASE WHEN COUNT(ret + value_weighted_market_return) OVER wb = 252
                     AND MIN(tdi) OVER wb = tdi - 252
                    THEN regr_slope(ret, value_weighted_market_return) OVER wb END AS beta_252
        FROM lagged
        -- Sector as of t-1: joined on the calendar's previous date, not this
        -- row's own date, so a code change effective at t is not visible until t+1.
        LEFT JOIN {sic_source} sic
          ON sic.permno = lagged.permno
         AND lagged.prev_date BETWEEN sic.start_date AND sic.end_date
        WINDOW wb AS ({W_BETA_T1})
    """


def _write_summary(con) -> None:
    exp = f"parquet_scan('{OUT.as_posix()}/**/*.parquet')"
    fp = f"parquet_scan('{FACTOR_PANEL.as_posix()}')"     # already ends in /**/*.parquet
    con.execute(f"""
        CREATE VIEW joined AS
        SELECT fp.date, exp.sector, exp.beta_252, exp.log_mcap
        FROM (SELECT permno, date, tdi FROM {fp} WHERE aligned) fp
        LEFT JOIN {exp} exp USING (permno, date, tdi)
    """)
    con.execute(f"""
        COPY (
            SELECT 'note' AS metric,
                'exposures are built over the full panel history through the '
                'last available date because they are inputs, not results; '
                'research use of factors/models/exposures must still stop at '
                '{LAST_RESEARCH_DATE} per the Week 2/3 seal' AS value
            UNION ALL SELECT 'exposure_rows', COUNT(*)::VARCHAR FROM {exp}
            UNION ALL SELECT 'aligned_factor_panel_rows', COUNT(*)::VARCHAR FROM joined
            UNION ALL SELECT 'sector_coverage_share_of_aligned',
                (COUNT(*) FILTER (sector IS NOT NULL) * 1.0 / COUNT(*))::VARCHAR FROM joined
            UNION ALL SELECT 'beta_252_coverage_share_of_aligned',
                (COUNT(*) FILTER (beta_252 IS NOT NULL) * 1.0 / COUNT(*))::VARCHAR FROM joined
            UNION ALL SELECT 'log_mcap_coverage_share_of_aligned',
                (COUNT(*) FILTER (log_mcap IS NOT NULL) * 1.0 / COUNT(*))::VARCHAR FROM joined
            UNION ALL SELECT 'sector_carried_forward_rows', COUNT(*)::VARCHAR FROM {exp}
                WHERE sector_carried_forward
            UNION ALL SELECT 'min_sectors_per_date', MIN(n)::VARCHAR FROM (
                SELECT COUNT(DISTINCT sector) AS n FROM joined WHERE sector IS NOT NULL GROUP BY date)
            UNION ALL SELECT 'mean_sectors_per_date', AVG(n)::VARCHAR FROM (
                SELECT COUNT(DISTINCT sector) AS n FROM joined WHERE sector IS NOT NULL GROUP BY date)
            UNION ALL SELECT 'max_sectors_per_date', MAX(n)::VARCHAR FROM (
                SELECT COUNT(DISTINCT sector) AS n FROM joined WHERE sector IS NOT NULL GROUP BY date)
            UNION ALL SELECT 'sector_' || COALESCE(sector::VARCHAR, 'NULL') || '_rows', COUNT(*)::VARCHAR
                FROM {exp} GROUP BY sector ORDER BY 1
        ) TO '{SUMMARY.as_posix()}' (HEADER, DELIMITER ',')
    """)


def main() -> None:
    import duckdb

    if not (ROOT / "data" / "processed" / "crsp_daily_panel").exists():
        sys.exit("Cleaned panel not found. Run src/data/clean_crsp.py first.")
    if not (ROOT / "data" / "processed" / "factor_panel").exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    if not RAW.exists():
        sys.exit(f"Raw file not found: {RAW}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    raw_source = f"read_csv('{RAW.as_posix()}', header=true, all_varchar=true)"
    # Materialised once: ~96,826 interval rows, reused by the join below instead
    # of rescanning the 23 GB export.
    con.execute(f"CREATE TABLE sic_intervals AS {sic_interval_query(raw_source)}")
    panel_source = f"parquet_scan('{PANEL_SOURCE.as_posix()}')"
    query = exposures_query(panel_source, "sic_intervals")
    con.execute(f"""
        COPY (
            SELECT *, EXTRACT(YEAR FROM date)::INTEGER AS year FROM ({query})
        ) TO '{OUT.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year), OVERWRITE_OR_IGNORE TRUE)
    """)
    _write_summary(con)
    print(con.sql(f"SELECT * FROM read_csv('{SUMMARY.as_posix()}')").df().to_string())
    print(f"\nWrote exposures: {OUT}")


if __name__ == "__main__":
    main()
