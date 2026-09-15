"""Market-neutral, position-capped, continuous-weight portfolio with staggered cohorts.

Construction, per formation date *t*, over the aligned cross-section:

1. take the cross-sectional percentile rank of the signal;
2. subtract the cross-sectional mean, which makes the book sum to zero;
3. scale so that gross exposure is 1;
4. cap each position at `CAP` of gross, then re-centre and re-scale until the
   cap holds. At ~1,660 names a rank-linear book puts ~0.12% in its largest
   position, so the cap does not bind here; it is in place for the smaller
   cross-sections and the far more concentrated model-driven signals of Week 4.

The book formed at *t* is held for the next 20 trading days, and a fresh one is
formed every day, so 20 cohorts are live at once and each carries 1/20 of the
capital. This replaces Week 2's single-offset rebalance, which used one start
date in twenty and could flip a factor's sign on that choice alone. The
aggregate weight is therefore a trailing sum over formation dates:

    W_i(d) = (1/20) * sum_{k=1..20} w_i(d-k)

which is a RANGE window over the trading-day index, so a gap in a stock's
history is handled by date arithmetic rather than by row counting.

P&L is marked daily: W_i(d) multiplies ret_i(d), the close(d-1)-to-close(d)
return. Since the signal forming cohort *t* is known at the close of *t*-1, each
position has a full day between signal and first accrual.

Trading convention: the book is rebalanced to its target weights W(d) at the
close of d-1. What is actually held going into that trade is yesterday's target
drifted by yesterday's returns, as a fraction of the grown NAV:

    H_i(d-1) = W_i(d-1) * (1 + ret_i(d-1)) / (1 + sum_j W_j(d-1) * ret_j(d-1))

so traded notional is sum_i |W_i(d) - H_i(d-1)|, TO(d) = traded / 2, and
net = gross - c * traded. An earlier version compared W(d) with W(d-1) directly,
which reports zero trading whenever cohort targets are unchanged even though
restoring them after a price move requires a trade (2026-09-14 review, item 1).

What this is and is not. It is a cost *overlay* on a daily-rebalanced target
book: gross P&L is target weights times returns, NAV growth uses the gross
return for every cost tier, costs are subtracted additively, and terminal
liquidation is charged in the same `traded` field as start-of-day trades. It
is not a cash-reconciled execution simulator, and it assumes every trade it
books is executable at the close -- including trades in names that have no
observation that day (a halt, a gap, a delisting), which are measured in
`traded_missing_execution_return` so that assumption has a size (2026-09-15
follow-up, item 3). A held name with no observation accrues 0 that day; if its next
observed row carries a multi-day return, it is marked at the weight then held,
which is the true weight only if the book did not change across the gap. That
ordinary halt/gap assumption is left open by design -- a stock can resume
trading mid-hold and the position should simply pick back up.

Event settlement (2026-09-15 round 3): a `delisting_flag = 'Y'` row is
different in kind from an ordinary gap -- the security will never trade again.
The event return is recognised normally on its own row, and from the day
after it the position's weight is forced to zero: it is treated as settled to
cash, not as ordinary equity a normal book. Otherwise the target weight
(computed from the cohort's static allocation, which knows nothing about
returns) stays at its stale pre-event level while the position's *value* has
moved, and the drift-aware trade math tries to "restore" that stale weight --
after a total loss this reads as repurchasing a wiped-out security. Settlement
converts that into a single correctly-sized exit trade on the day after the
event (the drifted post-event value moving to zero) and no further equity
exposure, `positions`/`gross_exposure` reporting, or missing-return flagging
for that name afterward. The freed capital is not redeployed; the book simply
runs under-invested by that amount until other cohorts roll off, which is a
disclosed simplification, not a defect.

Known versus unknown event proceeds (2026-09-15 round 4): the fix above
settles a name the day after *any* event row, whether or not that row's own
`ret` is known. When it is NULL, the standing missing-return policy already
accrues 0 that day and the drift term treats the unknown return as 0 too, so
the exit the following day converts the position to cash at its pre-event
value -- a disclosed zero-return imputation, not an observed payoff. This is
never restored to a tradable equity target (that would reopen round 3's
repurchase bug); it is reported separately as `gross_unknown_event_payoff` and
`names_settled_unknown_payoff` so the assumption has a visible size rather
than disappearing into the ordinary settlement figures.

`traded_missing_execution_return` measures the traded notional whose
*execution date* return is unobserved in this panel: since the trade recorded
on row *d* is placed at the close of *d*-1 (module docstring), the check is on
*d*-1's return (`ret_prev`), not *d*'s -- checking *d* checks the wrong day and
can both miss a real gap and flag an observed one, depending on which side of
the gap the missing row sits on (2026-09-15 round 3). `ret_prev` is computed
over every calendar day a name is tracked, not only days it is held, so the
very first day of a holding period is still checked against its true
predecessor. This is a return-availability proxy only (2026-09-15 round 4):
price and trading-status fields are not independently checked here, so it
neither confirms nor rules out a tradable closing price, and it says nothing
about whether a flow is a cash settlement rather than a market fill -- a
retained delisting event row is exactly the case where a return can be known
with no tradable price at all.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

CAP = 0.01
COSTS_BPS = [1, 5, 10, 20]
HOLD_DAYS = 20
TRADING_DAYS = 252


def capped_neutral_weights(frame: pd.DataFrame, signal: str, cap: float = CAP,
                           by: str = "date") -> pd.Series:
    """Per-date weights: zero net, gross at most 1, every position within `cap`.

    Gross is exactly 1 whenever the cap does not bind. When a cross-section is
    too small to reach gross 1 within the cap, the book is simply smaller. The
    two constraints genuinely conflict there, and re-scaling back to gross 1
    after clipping would quietly hand the cap back.
    """
    group = frame[by]
    centred = frame[signal] - frame.groupby(by)[signal].transform("mean")
    weights = centred / centred.abs().groupby(group).transform("sum")
    for _ in range(32):
        if weights.abs().max() <= cap + 1e-12:
            break
        weights = weights.clip(-cap, cap)
        weights = weights - weights.groupby(group).transform("mean")
    return weights.clip(-cap, cap)


def daily_book(con, panel_scan: str, first_date: str, last_date: str,
               factors=(), costs=COSTS_BPS, hold=HOLD_DAYS) -> pd.DataFrame:
    """Aggregate the live cohorts into a daily book and mark it to daily returns.

    Expects a registered `cohort` relation of (permno, tdi, w). The evaluation
    spine is every cohort name on every calendar day from formation through the
    day after expiry, left-joined to the panel so a stock that drops out of the
    panel mid-hold stays represented (NULL ret → positions_without_return) and
    still books a closing trade. Empty trailing windows coalesce to zero weight
    so the first accrual day records entry turnover. Remaining gross on the last
    evaluation day, marked at that day's close, is charged as terminal
    liquidation.

    `traded` is measured against drifted holdings, not yesterday's targets
    (module docstring). A missing `ret` drifts as 0, the same policy as the
    accrual. A `delisting_flag = 'Y'` row settles that name to cash from the
    following day (module docstring, "Event settlement"); when that row's own
    `ret` is NULL the settlement value is a disclosed zero-return assumption,
    not an observed payoff (module docstring, "Known versus unknown event
    proceeds").
    """
    exposures = ",\n            ".join(
        f"SUM(weight * (rank_{f} - 0.5)) AS exposure_{f}" for f in factors)
    rank_select = "".join(f", p.rank_{f} AS rank_{f}" for f in factors)
    daily = con.sql(f"""
        WITH calendar AS (
            SELECT date, tdi,
                   ANY_VALUE(value_weighted_market_return) AS value_weighted_market_return
            FROM {panel_scan}
            WHERE date BETWEEN DATE '{first_date}' AND DATE '{last_date}'
            GROUP BY date, tdi
        ), spine AS (
            SELECT DISTINCT c.permno, cal.date, cal.tdi, cal.value_weighted_market_return
            FROM cohort c
            JOIN calendar cal
              ON cal.tdi BETWEEN c.tdi AND c.tdi + {hold} + 1
             AND cal.date BETWEEN DATE '{first_date}' AND DATE '{last_date}'
        ), grid AS (
            SELECT spine.permno, spine.date, spine.tdi, p.ret, p.delisting_flag,
                   COALESCE(p.value_weighted_market_return, spine.value_weighted_market_return)
                       AS value_weighted_market_return
                   {rank_select}
            FROM spine
            LEFT JOIN {panel_scan} p USING (permno, tdi)
        ), settled AS (
            -- The first date this name is ever known to have delisted, from
            -- among the rows this book actually touches, and whether THAT
            -- row's own return is known. A row on or before this date is
            -- still ordinary equity; strictly after, it is cash -- known cash
            -- if event_return is not NULL, an assumed zero-return imputation
            -- otherwise (module docstring, "Known versus unknown event proceeds").
            SELECT permno, tdi AS settle_tdi, ret AS event_return
            FROM grid WHERE delisting_flag = 'Y'
            QUALIFY ROW_NUMBER() OVER (PARTITION BY permno ORDER BY tdi) = 1
        ), held AS (
            SELECT grid.*, s.settle_tdi, s.event_return,
                   CASE WHEN s.settle_tdi IS NOT NULL AND grid.tdi > s.settle_tdi THEN 0
                        ELSE COALESCE(SUM(COALESCE(cohort.w, 0)) OVER h, 0) / {hold} END AS weight,
                   CASE WHEN s.settle_tdi IS NOT NULL AND grid.tdi - 1 > s.settle_tdi THEN 0
                        ELSE COALESCE(SUM(COALESCE(cohort.w, 0)) OVER h_prev, 0) / {hold} END AS weight_prev,
                   -- Execution-day return, for the trade diagnostic below: was
                   -- there a valid close at tdi-1, the day this row's trade is
                   -- actually placed? Checked over every calendar day this
                   -- permno is tracked, not only days it is held, so an entry
                   -- trade is still checked against its true predecessor.
                   CASE WHEN LAG(grid.tdi) OVER p = grid.tdi - 1
                        THEN LAG(grid.ret) OVER p END AS ret_prev
            FROM grid LEFT JOIN cohort USING (permno, tdi)
            LEFT JOIN settled s USING (permno)
            WINDOW
                h AS (PARTITION BY permno ORDER BY tdi
                      RANGE BETWEEN {hold} PRECEDING AND 1 PRECEDING),
                h_prev AS (PARTITION BY permno ORDER BY tdi
                           RANGE BETWEEN {hold + 1} PRECEDING AND 2 PRECEDING),
                p AS (PARTITION BY permno ORDER BY tdi)
        ), live AS (
            SELECT * FROM held WHERE weight <> 0 OR weight_prev <> 0
        ), book AS (
            SELECT tdi, SUM(weight * COALESCE(ret, 0)) AS book_ret FROM live GROUP BY tdi
        ), nav AS (
            SELECT tdi, CASE WHEN LAG(tdi) OVER (ORDER BY tdi) = tdi - 1
                             THEN LAG(book_ret) OVER (ORDER BY tdi) ELSE 0 END AS book_ret_prev
            FROM book
        )
        SELECT date, tdi,
            -- Missing-return policy: a held name with NULL ret accrues 0 that
            -- day. Counted in positions_without_return; never dropped silently
            -- from the sum via SQL NULL-skipping. Exit-only rows (weight=0,
            -- ret NULL) also yield 0. A settled name reports weight=0 here, so
            -- it is no longer counted as an equity position at all.
            COALESCE(SUM(weight * COALESCE(ret, 0)), 0) AS gross_return,
            -- Traded against drifted holdings H = W_prev(1+ret_prev)/(1+book_ret_prev).
            SUM(ABS(weight - weight_prev * (1 + COALESCE(ret_prev, 0))
                                / (1 + book_ret_prev))) AS traded,
            -- Of that, trades whose execution day (tdi-1, not tdi) has no
            -- return in this panel: a return-availability proxy only, sized
            -- rather than hidden -- not a check of price, trading status, or
            -- settlement type (module docstring).
            COALESCE(SUM(ABS(weight - weight_prev * (1 + COALESCE(ret_prev, 0))
                                / (1 + book_ret_prev))) FILTER (ret_prev IS NULL), 0)
                AS traded_missing_execution_return,
            -- The settlement exit trade specifically, on names whose OWN event
            -- return was unknown: a disclosed zero-return imputation, reported
            -- separately from ordinary settlement so it is never mistaken for
            -- an observed payoff.
            COALESCE(SUM(ABS(weight_prev * (1 + COALESCE(ret_prev, 0)) / (1 + book_ret_prev)))
                FILTER (settle_tdi IS NOT NULL AND tdi = settle_tdi + 1 AND event_return IS NULL), 0)
                AS gross_unknown_event_payoff,
            COUNT(DISTINCT permno) FILTER (settle_tdi IS NOT NULL AND tdi = settle_tdi + 1
                                            AND event_return IS NULL) AS names_settled_unknown_payoff,
            SUM(weight) AS net_exposure,
            SUM(ABS(weight)) AS gross_exposure,
            -- Gross marked at this close: what a terminal liquidation would trade.
            SUM(ABS(weight * (1 + COALESCE(ret, 0)))) / (1 + ANY_VALUE(book_ret)) AS gross_close,
            -- The missing-execution-return share of that terminal trade,
            -- mirroring traded_missing_execution_return's own convention
            -- (checked against ret here, since a terminal trade executes at
            -- THIS day's own close, not the day before -- there is no
            -- "tomorrow" to place it at).
            COALESCE(SUM(ABS(weight * (1 + COALESCE(ret, 0)))) FILTER (ret IS NULL), 0)
                / (1 + ANY_VALUE(book_ret)) AS gross_close_missing_execution_return,
            COUNT(*) FILTER (weight <> 0) AS positions,
            COUNT(*) FILTER (weight <> 0 AND ret IS NULL) AS positions_without_return,
            -- Gross weight sitting in those names: the economic size of the
            -- 0-accrual assumption on this day, not just a count.
            COALESCE(SUM(ABS(weight)) FILTER (weight <> 0 AND ret IS NULL), 0) AS gross_without_return,
            MAX(ABS(weight)) AS max_abs_weight,
            ANY_VALUE(value_weighted_market_return) AS market_return,
            {exposures}
        FROM live JOIN nav USING (tdi) JOIN book USING (tdi)
        GROUP BY date, tdi ORDER BY tdi
    """).df()
    if len(daily) and float(daily.iloc[-1].gross_exposure) > 0:
        daily = daily.copy()
        last = daily.index[-1]
        daily.loc[last, "traded"] = float(daily.loc[last, "traded"]) + float(
            daily.loc[last, "gross_close"])
        daily.loc[last, "traded_missing_execution_return"] = float(
            daily.loc[last, "traded_missing_execution_return"]) + float(
            daily.loc[last, "gross_close_missing_execution_return"])
    daily = daily.drop(columns=["gross_close", "gross_close_missing_execution_return"])
    daily["turnover"] = daily.traded / 2.0
    for bps in costs:
        daily[f"net_return_{bps}bp"] = daily.gross_return - (bps / 1e4) * daily.traded
    return daily


def require_complete_marking(daily: pd.DataFrame) -> None:
    """Document missing-return exposure; do not abort the research run.

    Held names with NULL ``ret`` (delistings / panel gaps) accrue 0 under the
    policy in ``daily_book``. The count is required in every summary so a
    silent omission cannot recur. Raising here would refuse every CRSP-based
    book that touches a delisting mid-hold (~10^4 position-days).
    """
    if "positions_without_return" not in daily.columns:
        raise ValueError("daily book missing positions_without_return")


def performance_daily(returns: pd.Series, market: pd.Series = None) -> dict:
    """Annualised statistics for a daily return series."""
    mean, sd = returns.mean(), returns.std(ddof=1)
    growth = (1 + returns).cumprod()
    peak = growth.cummax().clip(lower=1.0)
    stats = {
        "annualised_return": mean * TRADING_DAYS,
        "annualised_volatility": sd * np.sqrt(TRADING_DAYS),
        "sharpe": mean / sd * np.sqrt(TRADING_DAYS),
        "hit_rate": (returns > 0).mean(),
        "max_drawdown": float((growth / peak - 1).min()),
    }
    if market is not None:
        aligned = pd.concat([returns, market], axis=1).dropna()
        stats["market_beta"] = float(
            aligned.cov().iloc[0, 1] / aligned.iloc[:, 1].var())
    return stats


def run(con, panel_scan: str, signal_frame: pd.DataFrame, signal: str,
        first_date: str, last_date: str, factors=(), cap: float = CAP) -> dict:
    """Form cohorts from `signal`, hold them 20 days, and mark the book daily."""
    cohort = signal_frame[["permno", "tdi", "date"]].copy()
    cohort["w"] = capped_neutral_weights(signal_frame, signal, cap)
    con.register("cohort", cohort[["permno", "tdi", "w"]])
    daily = daily_book(con, panel_scan, first_date, last_date, factors=factors)
    con.unregister("cohort")
    require_complete_marking(daily)

    summary = {
        "signal": signal, "days": len(daily),
        "first_date": str(daily.date.min().date()),
        "last_date": str(daily.date.max().date()),
        "mean_positions": daily.positions.mean(),
        "mean_gross_exposure": daily.gross_exposure.mean(),
        "mean_net_exposure": daily.net_exposure.mean(),
        "max_abs_net_exposure": daily.net_exposure.abs().max(),
        "largest_position": daily.max_abs_weight.max(),
        "cap": cap, "cap_binds": bool(daily.max_abs_weight.max() > cap - 1e-9),
        "mean_daily_turnover": daily.turnover.mean(),
        "annual_turnover_multiple": daily.turnover.mean() * TRADING_DAYS,
        "positions_without_return_per_day": daily.positions_without_return.mean(),
    }
    for column in ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]:
        for key, value in performance_daily(daily[column], daily.market_return).items():
            summary[f"{column}_{key}"] = value
    for factor in factors:
        summary[f"exposure_{factor}"] = daily[f"exposure_{factor}"].mean()
    return {"daily": daily, "summary": summary}
