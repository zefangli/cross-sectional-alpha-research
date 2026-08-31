"""Factor definitions.

Every expression is a DuckDB window expression over the daily panel, and every
named window is strictly backward-looking (`ROWS BETWEEN n PRECEDING AND m
PRECEDING` with `m >= 1`), so a factor observed at date *t* can never read a
return from *t* or later. Each factor also asserts window completeness -- the
count of observed returns and the earliest trading-day index in the window --
so a stock with a gap in its history yields NULL instead of a silently
short-window value.

Windows are positional (`ROWS`), which is why the `MIN(tdi)` guard is required:
it verifies that the k rows in the window really are the k consecutive trading
days ending at t-m.
"""

# Named windows shared by the factor expressions. `tdi` is a dense trading-day
# index over the panel calendar, so `tdi - k` is "k trading days ago".
WINDOWS = {
    # t-120 .. t-21: medium-term momentum, skipping the most recent month
    "w_mom": "PARTITION BY permno ORDER BY tdi ROWS BETWEEN 120 PRECEDING AND 21 PRECEDING",
}

FACTOR_SQL = {
    "mom_120_20": """
        CASE WHEN COUNT(ret) OVER w_mom = 100
              AND MIN(tdi) OVER w_mom = tdi - 120
             THEN PRODUCT(1 + ret) OVER w_mom - 1 END
    """,
}

# Sign of the economic hypothesis: +1 means high factor -> high forward return.
FACTOR_SIGN = {
    "mom_120_20": +1,
}


def factor_query(source: str, name: str) -> str:
    """Panel rows plus one factor column, keeping panel keys, target and flags."""
    windows = ",\n                ".join(f"{k} AS ({v})" for k, v in WINDOWS.items())
    return f"""
        WITH calendar AS (
            SELECT date, ROW_NUMBER() OVER (ORDER BY date) - 1 AS tdi
            FROM (SELECT DISTINCT date FROM {source})
        )
        SELECT permno, date, tdi, eligibility_flag, forward_return_20d,
               ({FACTOR_SQL[name]}) AS f
        FROM {source} JOIN calendar USING (date)
        WINDOW
                {windows}
    """
