"""Week 5 robustness suite for the pre-registered six-factor composite.

Pre-declared in `experiments.csv` as W5-004 and W5-005, run against the SAME
book `week4_models.py` already established: the equal-weighted signed-rank
composite of the six Week 0 factors, formed on the continuous 2014-01-02 ..
2023-11-30 span and marked to 2023-12-29, under both rank and decile
weighting. No model prediction and no Week 5 exposure/neutralisation input is
needed here -- this module only re-slices and re-costs the existing composite.

The headline this suite must be read against, from `week4_models.py`: gross
Sharpe 0.297, HAC t = 1.01 over 2014-2023. That t-statistic means the
composite is not distinguishable from a zero-mean series. Every slice below
-- by factor dropped, by volatility tercile, by year, by cost, by rebalance
horizon -- is therefore a slice of noise, and slicing noise finely produces
dispersion by construction: some slice will look strong and some weak with no
underlying regime or mechanism behind either. The dispersion itself, not the
best or worst slice, is what each output records.

Local variants of `week4_models.composite_frame`/`book`/`summarize` are used
here rather than importing them, because the ablation experiment needs an
arbitrary factor subset (not just the full six) and the rebalance-horizon
experiment needs a `last_date` cohort cutoff that shifts with the hold length
-- both of which `week4_models`'s versions hard-code. `src/portfolio/backtest`
(cohort weighting, the daily SQL book, annualised stats) and
`src/evaluation/factor_eval.newey_west_tstat` do all the actual estimation;
nothing here reimplements them.

Two windows, as in Week 3/4: cohort formation stops at COHORT_LAST (the last
formation date whose 20-day hold still ends in 2023), P&L is marked to
PNL_LAST so those last cohorts finish their hold. For the rebalance-horizon
variants the formation cutoff shifts with the hold length so every horizon's
last cohort still finishes inside 2023 -- see `cohort_cutoff`. No stage here
reads 2024-2025.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.evaluation.factor_eval import newey_west_tstat, OVERLAP_LAG
from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.models.splits import walk_forward_splits
from src.models.walk_forward import COHORT_LAST
from src.portfolio.backtest import (COSTS_BPS, HOLD_DAYS, TRADING_DAYS,
                                     capped_neutral_weights, daily_book, performance_daily)

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
OUT = ROOT / "reports" / "week5"
PNL_LAST = "2023-12-31"
WEIGHTINGS = ("rank", "decile")
REBALANCE_HORIZONS = (5, 10, 20, 40)   # pre-declared; not a horizon search
COST_SWEEP_BPS = list(range(0, 31))    # 0..30bp, fine enough to draw a curve
VOL_WINDOW = 20                        # trailing window for the regime split


def composite_frame(con, scan: str, first_date: str, last_date: str) -> pd.DataFrame:
    """(permno, date, tdi, rank_<factor>) rows over [first_date, last_date]."""
    columns = ", ".join(f"rank_{f}" for f in ALL_FACTORS)
    return con.sql(f"""
        SELECT permno, date, tdi, {columns}
        FROM {scan}
        WHERE aligned AND date >= DATE '{first_date}' AND date <= DATE '{last_date}'
        ORDER BY tdi
    """).df()


def add_signal(frame: pd.DataFrame, factors) -> pd.DataFrame:
    """Equal-weighted signed-rank composite over `factors`, plus its decile bucket."""
    frame = frame.copy()
    frame["rank"] = sum(FACTOR_SIGN[f] * frame[f"rank_{f}"] for f in factors) / len(factors)
    pct = frame.groupby("date")["rank"].rank(pct=True)
    frame["decile"] = np.where(pct >= 0.9, 1.0, np.where(pct <= 0.1, -1.0, 0.0))
    return frame


def book(con, scan: str, frame: pd.DataFrame, weighting: str, first_date: str,
         last_date: str, hold: int = HOLD_DAYS) -> pd.DataFrame:
    """Form cohorts on every date in `frame`, hold `hold` days, mark P&L in one call."""
    cohort = frame[["permno", "tdi", "date"]].copy()
    cohort["w"] = capped_neutral_weights(frame, weighting)
    con.register("cohort", cohort[["permno", "tdi", "w"]])
    daily = daily_book(con, scan, first_date, last_date, hold=hold)
    con.unregister("cohort")
    return daily


def summarize(daily: pd.DataFrame) -> dict:
    """Book statistics: annualised performance plus the 20-lag HAC t-stat and breakeven."""
    summary = {
        "days": len(daily),
        "annual_turnover": daily.turnover.mean() * TRADING_DAYS,
        "breakeven_bp": 1e4 * daily.gross_return.mean() / daily.traded.mean(),
    }
    for column in ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]:
        for key, value in performance_daily(daily[column], daily.market_return).items():
            summary[f"{column}_{key}"] = value
    summary["hac_t"] = newey_west_tstat(daily.gross_return, OVERLAP_LAG)
    return summary


def sharpe_hac(returns: pd.Series) -> dict:
    """Gross Sharpe and 20-lag HAC t on an arbitrary sub-series of daily returns."""
    mean, sd = returns.mean(), returns.std(ddof=1)
    return {"days": len(returns), "gross_sharpe": mean / sd * np.sqrt(TRADING_DAYS),
            "hac_t": newey_west_tstat(returns, OVERLAP_LAG)}


def cohort_cutoff(con, scan: str, pnl_last: str, hold: int) -> str:
    """Last formation date whose `hold`-day hold still ends by `pnl_last`.

    Mirrors how COHORT_LAST=2023-11-30 relates to PNL_LAST for hold=20 (the
    default): both are `hold` trading days apart on the panel's own `tdi`.
    Verified in `main` to reproduce COHORT_LAST exactly at hold=20.
    """
    tdi_end = con.sql(f"SELECT MAX(tdi) FROM {scan} WHERE date <= DATE '{pnl_last}'").fetchone()[0]
    cutoff = con.sql(f"SELECT MIN(date) FROM {scan} WHERE tdi = {tdi_end - hold}").fetchone()[0]
    return str(cutoff)


def ablation_table(con, scan: str, raw_frame: pd.DataFrame, first_date: str) -> pd.DataFrame:
    """W5-004: rebuild the composite dropping each factor in turn, both weightings."""
    frames = {"full": add_signal(raw_frame, ALL_FACTORS)}
    for dropped in ALL_FACTORS:
        kept = [f for f in ALL_FACTORS if f != dropped]
        frames[dropped] = add_signal(raw_frame, kept)

    rows = []
    for label, frame in frames.items():
        for weighting in WEIGHTINGS:
            daily = book(con, scan, frame, weighting, first_date, PNL_LAST)
            s = summarize(daily)
            rows.append({
                "dropped": label, "weighting": weighting,
                "gross_sharpe": s["gross_return_sharpe"], "hac_t": s["hac_t"],
                "net_sharpe_1bp": s["net_return_1bp_sharpe"],
                "net_sharpe_5bp": s["net_return_5bp_sharpe"],
                "net_sharpe_10bp": s["net_return_10bp_sharpe"],
                "net_sharpe_20bp": s["net_return_20bp_sharpe"],
                "breakeven_bp": s["breakeven_bp"],
                "annual_turnover": s["annual_turnover"],
                "beta": s["gross_return_market_beta"],
            })
    return pd.DataFrame(rows)


def regime_table(full: dict) -> pd.DataFrame:
    """Split by trailing market-vol tercile: a window ending t-1, not a full-sample split."""
    market = full["rank"][["date", "market_return"]].drop_duplicates().sort_values("date")
    market["trail_vol"] = (market.market_return.shift(1)
                            .rolling(VOL_WINDOW).std() * np.sqrt(TRADING_DAYS))
    market["tercile"] = pd.qcut(market.trail_vol, 3, labels=["low", "mid", "high"])

    rows = []
    for weighting, daily in full.items():
        merged = daily.merge(market[["date", "tercile", "trail_vol"]], on="date")
        for tercile in ["low", "mid", "high"]:
            g = merged.loc[merged.tercile == tercile]
            stats = sharpe_hac(g.gross_return)
            rows.append({"weighting": weighting, "tercile": tercile,
                        "mean_trailing_vol": g.trail_vol.mean(), **stats})
    return pd.DataFrame(rows)


def subperiod_table(full: dict) -> pd.DataFrame:
    """Sharpe/HAC t by calendar year and by pre/post half of the marked series."""
    rows = []
    for weighting, daily in full.items():
        daily = daily.sort_values("date").reset_index(drop=True)
        for year, g in daily.assign(year=daily.date.dt.year).groupby("year"):
            rows.append({"weighting": weighting, "period": str(year),
                        "first_date": str(g.date.min().date()), "last_date": str(g.date.max().date()),
                        **sharpe_hac(g.gross_return)})
        half = len(daily) // 2
        for label, g in [("pre_half", daily.iloc[:half]), ("post_half", daily.iloc[half:])]:
            rows.append({"weighting": weighting, "period": label,
                        "first_date": str(g.date.min().date()), "last_date": str(g.date.max().date()),
                        **sharpe_hac(g.gross_return)})
    return pd.DataFrame(rows)


def cost_curve_table(full: dict) -> pd.DataFrame:
    """Sharpe versus assumed cost, 0-30bp, both weightings."""
    rows = []
    for weighting, daily in full.items():
        for bps in COST_SWEEP_BPS:
            net = daily.gross_return - (bps / 1e4) * daily.traded
            rows.append({"weighting": weighting, "cost_bp": bps,
                        "sharpe": net.mean() / net.std(ddof=1) * np.sqrt(TRADING_DAYS),
                        "mean_annual_return": net.mean() * TRADING_DAYS})
    return pd.DataFrame(rows)


def rebalance_table(con, scan: str, first_date: str) -> pd.DataFrame:
    """W5-005 part 2: {5,10,20,40}-day holds, each with its own 2023 cutoff."""
    rows = []
    for hold in REBALANCE_HORIZONS:
        cutoff = cohort_cutoff(con, scan, PNL_LAST, hold)
        frame = add_signal(composite_frame(con, scan, first_date, cutoff), ALL_FACTORS)
        for weighting in WEIGHTINGS:
            daily = book(con, scan, frame, weighting, first_date, PNL_LAST, hold=hold)
            s = summarize(daily)
            rows.append({
                "horizon_days": hold, "cutoff_date": cutoff, "weighting": weighting,
                "days": s["days"], "gross_sharpe": s["gross_return_sharpe"], "hac_t": s["hac_t"],
                "net_sharpe_10bp": s["net_return_10bp_sharpe"],
                "annual_turnover": s["annual_turnover"], "breakeven_bp": s["breakeven_bp"],
            })
    return pd.DataFrame(rows)


def figure(full: dict, ablation: pd.DataFrame, regimes: pd.DataFrame,
           cost_curve: pd.DataFrame, rebalance: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    for weighting, daily in full.items():
        d = daily.set_index("date")
        (1 + d.gross_return).cumprod().plot(ax=ax[0, 0], lw=1, label=weighting)
    ax[0, 0].set_title("Full composite: cumulative gross return, 2014-2023")
    ax[0, 0].legend(fontsize=8)

    piv = ablation.query("weighting == 'rank'").set_index("dropped")["net_sharpe_10bp"]
    order = ["full"] + [f for f in ALL_FACTORS]
    piv = piv.reindex(order)
    colors = ["k"] + ["C0"] * len(ALL_FACTORS)
    ax[0, 1].bar(range(len(piv)), piv.values, color=colors)
    ax[0, 1].axhline(0, color="k", lw=0.8)
    ax[0, 1].set_xticks(range(len(piv)), piv.index, rotation=45, ha="right", fontsize=7)
    ax[0, 1].set_title("Ablation: net Sharpe at 10bp, rank weighting")

    for weighting in WEIGHTINGS:
        g = cost_curve.query("weighting == @weighting")
        ax[1, 0].plot(g.cost_bp, g.sharpe, marker="o", ms=2, label=weighting)
    ax[1, 0].axhline(0, color="k", lw=0.8)
    ax[1, 0].set_xlabel("cost, bp of traded notional")
    ax[1, 0].set_title("Sharpe versus assumed cost, 0-30bp")
    ax[1, 0].legend(fontsize=8)

    width = 0.35
    for i, weighting in enumerate(WEIGHTINGS):
        g = regimes.query("weighting == @weighting").set_index("tercile").reindex(["low", "mid", "high"])
        x = np.arange(3) + (i - 0.5) * width
        ax[1, 1].bar(x, g.gross_sharpe, width, label=weighting)
    ax[1, 1].axhline(0, color="k", lw=0.8)
    ax[1, 1].set_xticks(range(3), ["low", "mid", "high"])
    ax[1, 1].set_xlabel("trailing market-vol tercile")
    ax[1, 1].set_title("Gross Sharpe by volatility regime")
    ax[1, 1].legend(fontsize=8)

    fig.suptitle("Week 5 robustness: pre-registered composite, 2014-2023 (HAC t ~1.0, read with caution)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"

    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)
    first_date = str(splits.validation_start.min())
    assert cohort_cutoff(con, scan, PNL_LAST, HOLD_DAYS) == COHORT_LAST, \
        "tdi-based cutoff must reproduce the pre-declared COHORT_LAST at the default 20-day hold"

    raw_frame = composite_frame(con, scan, first_date, COHORT_LAST)
    full = {w: book(con, scan, add_signal(raw_frame, ALL_FACTORS), w, first_date, PNL_LAST)
            for w in WEIGHTINGS}
    full_summary = {w: summarize(full[w]) for w in WEIGHTINGS}
    assert abs(full_summary["rank"]["gross_return_sharpe"] - 0.297) < 0.01, \
        "recomputed composite must reproduce the Week 4 headline gross Sharpe"
    assert abs(full_summary["rank"]["hac_t"] - 1.01) < 0.05, \
        "recomputed composite must reproduce the Week 4 headline HAC t"
    print("Full composite (rank weighting) reproduces the Week 4 headline: "
          f"gross Sharpe {full_summary['rank']['gross_return_sharpe']:.3f}, "
          f"HAC t {full_summary['rank']['hac_t']:.2f}\n")

    ablation = ablation_table(con, scan, raw_frame, first_date)
    ablation.to_csv(OUT / "ablation.csv", index=False)
    print("Ablation (W5-004):\n", ablation.round(4).to_string(index=False), "\n")

    regimes = regime_table(full)
    regimes.to_csv(OUT / "regimes.csv", index=False)
    print("Volatility-regime split:\n", regimes.round(4).to_string(index=False), "\n")

    subperiods = subperiod_table(full)
    subperiods.to_csv(OUT / "subperiods.csv", index=False)
    print("Sub-period split:\n", subperiods.round(4).to_string(index=False), "\n")

    cost_curve = cost_curve_table(full)
    cost_curve.to_csv(OUT / "cost_curve.csv", index=False)
    breakevens = {w: full_summary[w]["breakeven_bp"] for w in WEIGHTINGS}
    print(f"Cost curve breakeven (analytic, matches the sweep's zero-crossing): {breakevens}\n")

    rebalance = rebalance_table(con, scan, first_date)
    rebalance.to_csv(OUT / "rebalance.csv", index=False)
    print("Rebalance-horizon check (W5-005):\n", rebalance.round(4).to_string(index=False), "\n")

    figure(full, ablation, regimes, cost_curve, rebalance, OUT / "diagnostics.png")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
