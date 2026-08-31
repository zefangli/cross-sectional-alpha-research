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

Turnover is TO(d) = 0.5 * sum_i |W_i(d) - W_i(d-1)| and cost is charged on the
traded notional sum_i |dW|, so net = gross - 2 * c * TO, matching Week 2.
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

    Expects a registered `cohort` relation of (permno, tdi, w). Rows of the
    panel outside the aligned set are still consulted, so a stock that stops
    being eligible mid-holding keeps being marked rather than silently vanishing.
    """
    exposures = ",\n            ".join(
        f"SUM(weight * (rank_{f} - 0.5)) AS exposure_{f}" for f in factors)
    daily = con.sql(f"""
        WITH grid AS (
            SELECT permno, date, tdi, ret, value_weighted_market_return
                   {''.join(f', rank_{f}' for f in factors)}
            FROM {panel_scan}
            WHERE date BETWEEN DATE '{first_date}' AND DATE '{last_date}'
        ), held AS (
            SELECT grid.*,
                   SUM(COALESCE(cohort.w, 0)) OVER h / {hold} AS weight,
                   SUM(COALESCE(cohort.w, 0)) OVER h_prev / {hold} AS weight_prev
            FROM grid LEFT JOIN cohort USING (permno, tdi)
            WINDOW
                h AS (PARTITION BY permno ORDER BY tdi
                      RANGE BETWEEN {hold} PRECEDING AND 1 PRECEDING),
                h_prev AS (PARTITION BY permno ORDER BY tdi
                           RANGE BETWEEN {hold + 1} PRECEDING AND 2 PRECEDING)
        )
        SELECT date, tdi,
            SUM(weight * ret) AS gross_return,
            SUM(ABS(weight - weight_prev)) AS traded,
            SUM(weight) AS net_exposure,
            SUM(ABS(weight)) AS gross_exposure,
            COUNT(*) FILTER (weight <> 0) AS positions,
            COUNT(*) FILTER (weight <> 0 AND ret IS NULL) AS positions_without_return,
            MAX(ABS(weight)) AS max_abs_weight,
            ANY_VALUE(value_weighted_market_return) AS market_return,
            {exposures}
        FROM held
        WHERE weight <> 0 OR weight_prev <> 0
        GROUP BY date, tdi ORDER BY tdi
    """).df()
    daily["turnover"] = daily.traded / 2.0
    for bps in costs:
        daily[f"net_return_{bps}bp"] = daily.gross_return - (bps / 1e4) * daily.traded
    return daily


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
