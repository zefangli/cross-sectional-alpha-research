"""Factor definitions.

Every expression is a DuckDB window expression over the daily panel, and every
named window ends at *t*-1 or earlier, so every factor is fully determined by
the close of *t*-1.

That one-day gap is a tradability requirement, not just a leakage guard. The
target is the return from the close of *t* to the close of *t*+20, so a signal
that still needs *t*'s own close could only be traded at that same close. All
six factors therefore leave a full day between their last input and the start of
the target: the signal is known at the close of *t*-1 and can be executed any
time during *t*.

Each factor also asserts window completeness: the count of observed inputs and
the earliest trading-day index in the window. A stock with a gap in its history
yields NULL instead of a silently short-window value. Windows are positional
(`ROWS`), which is why the `MIN(tdi)` guard is required -- it verifies that the
k rows in the window really are the k consecutive trading days ending at t-m.

Split handling: in this CRSP export `price`, `volume` and `shares_outstanding`
are as-traded, not split-adjusted (verified on the 2014 7:1 Apple split), while
`ret` is adjusted. Factors therefore never read a raw price level or a raw share
volume. Drawdown is measured on a cumulative total-return index, and volume
surprise on share turnover (volume / shares outstanding), both of which are
invariant to splits.
"""

# Named windows shared by the factor expressions. `tdi` is a dense trading-day
# index over the panel calendar, so `tdi - k` is "k trading days ago".
_PARTITION = "PARTITION BY permno ORDER BY tdi ROWS BETWEEN"
WINDOWS = {
    # t-120 .. t-21: medium-term momentum, skipping the most recent month
    "w_mom": f"{_PARTITION} 120 PRECEDING AND 21 PRECEDING",
    # t-5 .. t-1: short-term reversal
    "w_rev": f"{_PARTITION} 5 PRECEDING AND 1 PRECEDING",
    # t-20 .. t-1: realised volatility
    "w_vol": f"{_PARTITION} 20 PRECEDING AND 1 PRECEDING",
    # t-21 .. t-2: the 20 days before the lagged turnover observation at t-1
    "w_vs": f"{_PARTITION} 21 PRECEDING AND 2 PRECEDING",
    # t-272 .. t-21: 252-day market-model estimation window ending where the
    # residual-momentum window ends, so the momentum window is a subset of it
    "w_beta": f"{_PARTITION} 272 PRECEDING AND 21 PRECEDING",
    # t-252 .. t-1: one-year running peak, ending at the lagged observation
    "w_peak": f"{_PARTITION} 252 PRECEDING AND 1 PRECEDING",
}

_MKT = "value_weighted_market_return"

FACTOR_SQL = {
    # 5.1 medium-term momentum: compounded return over t-120 .. t-21
    "mom_120_20": """
        CASE WHEN COUNT(ret) OVER w_mom = 100
              AND MIN(tdi) OVER w_mom = tdi - 120
             THEN PRODUCT(1 + ret) OVER w_mom - 1 END
    """,
    # 5.2 short-term reversal: minus the sum of the last five daily returns, so
    # a high value means a recent loser and the sign convention stays positive
    "rev_5": """
        CASE WHEN COUNT(ret) OVER w_rev = 5
              AND MIN(tdi) OVER w_rev = tdi - 5
             THEN -SUM(ret) OVER w_rev END
    """,
    # 5.3 realised volatility over the last 20 trading days, not annualised
    "rvol_20": """
        CASE WHEN COUNT(ret) OVER w_vol = 20
              AND MIN(tdi) OVER w_vol = tdi - 20
             THEN SQRT(SUM(ret * ret) OVER w_vol) END
    """,
    # 5.4 volume surprise: log of the previous day's share turnover against its
    # own trailing 20-day mean. Turnover rather than share volume, because a
    # split multiplies volume and shares outstanding together and cancels out of
    # the ratio. Lagged to t-1 so the signal does not need t's own close.
    "vs_20": """
        CASE WHEN COUNT(turnover) OVER w_vs = 20
              AND MIN(tdi) OVER w_vs = tdi - 21
              AND turnover_lag1 > 0 AND AVG(turnover) OVER w_vs > 0
             THEN LN(turnover_lag1 / (AVG(turnover) OVER w_vs)) END
    """,
    # 5.5 residual momentum: fit r_i = alpha + beta * r_m over the 252 days
    # ending at t-21, then sum the implied residuals over t-120 .. t-21. The
    # sum of residuals expands to closed form in window aggregates:
    #   sum(e) = sum(r) - n*alpha - beta*sum(r_m)
    # so no per-row residual column is needed.
    "rmom_120_20": f"""
        CASE WHEN COUNT(ret + {_MKT}) OVER w_mom = 100
              AND MIN(tdi) OVER w_mom = tdi - 120
              AND COUNT(ret + {_MKT}) OVER w_beta = 252
              AND MIN(tdi) OVER w_beta = tdi - 272
             THEN SUM(ret) OVER w_mom
                  - 100 * (regr_intercept(ret, {_MKT}) OVER w_beta)
                  - (regr_slope(ret, {_MKT}) OVER w_beta) * (SUM({_MKT}) OVER w_mom)
        END
    """,
    # 5.6 drawdown from the one-year peak of the cumulative total-return index,
    # measured as at t-1 so the signal does not need t's own close. Zero means
    # the stock closed at its 252-day high; the value is never positive. `cum`
    # is a running index whose base cancels out of the ratio, so only the
    # 252-day window itself has to be complete.
    "dd_252": """
        CASE WHEN COUNT(ret) OVER w_peak = 252
              AND MIN(tdi) OVER w_peak = tdi - 252
             THEN cum_lag1 / (MAX(cum) OVER w_peak) - 1 END
    """,
}

# Sign of the pre-registered hypothesis: +1 means high factor -> high forward
# return. Recorded before the factor was evaluated; see experiments.csv.
FACTOR_SIGN = {
    "mom_120_20": +1,    # winners keep winning
    "rev_5": +1,         # recent losers bounce (factor is already negated)
    "rvol_20": -1,       # low-volatility anomaly: high volatility underperforms
    "vs_20": +1,         # high-volume return premium (Gervais/Kaniel/Mingelgrin)
    "rmom_120_20": +1,   # momentum in market-model residuals
    "dd_252": +1,        # proximity to the 52-week high predicts strength
}

ALL_FACTORS = list(FACTOR_SQL)


def factor_query(source: str, name: str) -> str:
    """Panel rows plus one factor column, keeping panel keys, target and flags."""
    windows = ",\n                ".join(f"{k} AS ({v})" for k, v in WINDOWS.items())
    return f"""
        WITH calendar AS (
            SELECT date, ROW_NUMBER() OVER (ORDER BY date) - 1 AS tdi
            FROM (SELECT DISTINCT date FROM {source})
        ), base AS (
            SELECT permno, date, tdi, eligibility_flag, forward_return_20d,
                   ret, {_MKT},
                   volume / NULLIF(shares_outstanding, 0) AS turnover,
                   PRODUCT(1 + ret) OVER (
                       PARTITION BY permno ORDER BY tdi
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum
            FROM {source} JOIN calendar USING (date)
        ), lagged AS (
            -- Yesterday's values, but only when yesterday really is t-1 for this
            -- stock; a gap in its history leaves these NULL rather than reaching
            -- further back.
            SELECT base.*,
                   CASE WHEN LAG(tdi) OVER p = tdi - 1
                        THEN LAG(turnover) OVER p END AS turnover_lag1,
                   CASE WHEN LAG(tdi) OVER p = tdi - 1
                        THEN LAG(cum) OVER p END AS cum_lag1
            FROM base
            WINDOW p AS (PARTITION BY permno ORDER BY tdi)
        )
        SELECT permno, date, tdi, eligibility_flag, forward_return_20d,
               ({FACTOR_SQL[name]}) AS f
        FROM lagged
        WINDOW
                {windows}
    """
