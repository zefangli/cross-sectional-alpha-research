"""Week 3 baseline: cross-factor structure, walk-forward splits, and one
reproducible end-to-end portfolio run.

Everything here stops at the sealed period. Cohorts are formed on dates whose
20-day holding window ends inside 2023, and P&L is marked to the end of 2023.
No model is fitted; the only signals are the six factors and an equal-weighted
composite of their signed ranks, declared before the run.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.models.splits import walk_forward_splits
from src.portfolio.backtest import COSTS_BPS, run

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
OUT = ROOT / "reports" / "week3"
COHORT_LAST = "2023-11-30"   # last formation date whose 20-day hold ends in 2023
PNL_LAST = "2023-12-31"
COMPOSITE = "composite"


def rank_correlations(con, scan: str, last_date: str) -> pd.DataFrame:
    """Mean daily cross-sectional Spearman correlation between factor ranks."""
    pairs = [(a, b) for i, a in enumerate(ALL_FACTORS) for b in ALL_FACTORS[i:]]
    selects = ",\n            ".join(
        f"AVG(c_{a}_{b}) AS c_{a}_{b}" for a, b in pairs)
    daily = ",\n            ".join(
        f"corr(rank_{a}, rank_{b}) AS c_{a}_{b}" for a, b in pairs)
    row = con.sql(f"""
        SELECT {selects} FROM (
            SELECT date, {daily} FROM {scan}
            WHERE aligned AND date <= DATE '{last_date}' GROUP BY date)
    """).df().iloc[0]
    matrix = pd.DataFrame(index=ALL_FACTORS, columns=ALL_FACTORS, dtype=float)
    for a, b in pairs:
        matrix.loc[a, b] = matrix.loc[b, a] = row[f"c_{a}_{b}"]
    return matrix


def figure(returns: pd.DataFrame, summary: pd.DataFrame, correlation: pd.DataFrame,
           composite_daily: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(returns.columns)
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))

    (1 + returns).cumprod().plot(ax=ax[0, 0], lw=1)
    ax[0, 0].set_title("Cumulative gross return, daily-marked staggered cohorts")
    ax[0, 0].legend(fontsize=7)

    costs = [0] + COSTS_BPS
    for name in names:
        sharpes = [summary.loc["gross_return_sharpe", name]] + [
            summary.loc[f"net_return_{b}bp_sharpe", name] for b in COSTS_BPS]
        ax[0, 1].plot(costs, sharpes, marker="o", ms=3, label=name)
    ax[0, 1].axhline(0, color="k", lw=0.8)
    ax[0, 1].set_xlabel("cost, bp of traded notional")
    ax[0, 1].set_title("Sharpe versus assumed cost")
    ax[0, 1].legend(fontsize=7)

    labels = list(correlation.columns)
    image = ax[1, 0].imshow(correlation, cmap="RdBu_r", vmin=-1, vmax=1)
    ax[1, 0].set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=7)
    ax[1, 0].set_yticks(range(len(labels)), labels, fontsize=7)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax[1, 0].text(j, i, f"{correlation.iloc[i, j]:.2f}",
                          ha="center", va="center", fontsize=6)
    fig.colorbar(image, ax=ax[1, 0], fraction=0.046)
    ax[1, 0].set_title("Daily gross portfolio-return correlation")

    rolling = composite_daily.set_index("date")
    beta = (rolling.gross_return.rolling(252).cov(rolling.market_return)
            / rolling.market_return.rolling(252).var())
    beta.plot(ax=ax[1, 1], lw=1)
    ax[1, 1].axhline(0, color="k", lw=0.8)
    ax[1, 1].set_title("Composite book: rolling 252-day market beta")

    fig.suptitle("Week 3 baseline: rank-weighted, dollar-neutral, capped, "
                 "20-day staggered cohorts")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"

    # 1. Cross-factor rank correlation.
    ranks = rank_correlations(con, scan, COHORT_LAST)
    ranks.to_csv(OUT / "factor_rank_correlation.csv")
    print("Mean daily cross-sectional rank correlation:\n", ranks.round(3).to_string(), "\n")

    # 2. Fixed walk-forward splits.
    dates = con.sql(
        f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)
    splits.to_csv(OUT / "walk_forward_splits.csv", index=False)
    print("Walk-forward splits:\n", splits.to_string(index=False), "\n")

    # 3. Signals: the six factors in their hypothesised direction, plus an
    #    equal-weighted composite of the signed ranks.
    signal_frame = con.sql(f"""
        SELECT permno, date, tdi, {', '.join(f'rank_{f}' for f in ALL_FACTORS)}
        FROM {scan} WHERE aligned AND date <= DATE '{COHORT_LAST}' ORDER BY tdi
    """).df()
    for factor in ALL_FACTORS:
        signal_frame[f"signal_{factor}"] = FACTOR_SIGN[factor] * signal_frame[f"rank_{factor}"]
    signal_frame[f"signal_{COMPOSITE}"] = signal_frame[
        [f"signal_{f}" for f in ALL_FACTORS]].mean(axis=1)

    # The same six signals weighted by tail decile instead of by rank. Centring
    # and gross-normalising a +1/0/-1 indicator reproduces the equal-weighted
    # decile-10-minus-decile-1 book exactly, so this is Week 2's weighting run
    # through Week 3's estimator and the comparison isolates the weighting.
    for factor in ALL_FACTORS:
        rank = signal_frame[f"rank_{factor}"]
        signal_frame[f"decile_{factor}"] = FACTOR_SIGN[factor] * np.where(
            rank >= 0.9, 1.0, np.where(rank <= 0.1, -1.0, 0.0))
    composite_rank = signal_frame.groupby("date")[f"signal_{COMPOSITE}"].rank(pct=True)
    signal_frame[f"decile_{COMPOSITE}"] = np.where(
        composite_rank >= 0.9, 1.0, np.where(composite_rank <= 0.1, -1.0, 0.0))
    print(f"Cohort rows: {len(signal_frame):,}\n")

    # 4. One portfolio per signal, under each weighting.
    summaries, first_date = [], str(signal_frame.date.min().date())
    for weighting in ("signal", "decile"):
        for name in ALL_FACTORS + [COMPOSITE]:
            label = name if weighting == "signal" else f"{name}__decile"
            result = run(con, scan, signal_frame, f"{weighting}_{name}",
                         first_date, PNL_LAST, factors=ALL_FACTORS)
            result["daily"].to_csv(OUT / f"daily_{label}.csv", index=False)
            summaries.append(pd.Series(result["summary"], name=label))
            print(f"{label:22s} gross SR {result['summary']['gross_return_sharpe']:6.3f}"
                  f"  net@10bp {result['summary']['net_return_10bp_sharpe']:6.3f}"
                  f"  turnover/yr {result['summary']['annual_turnover_multiple']:6.1f}"
                  f"  gross exp {result['summary']['mean_gross_exposure']:5.3f}"
                  f"  beta {result['summary']['gross_return_market_beta']:6.3f}", flush=True)
    summary = pd.concat(summaries, axis=1)
    summary.to_csv(OUT / "portfolio_summary.csv")

    # 5. Correlation of the daily portfolio returns.
    books = {name: pd.read_csv(OUT / f"daily_{name}.csv", parse_dates=["date"])
             for name in ALL_FACTORS + [COMPOSITE]}
    returns = pd.DataFrame({name: book.set_index("date").gross_return
                            for name, book in books.items()})
    correlation = returns[ALL_FACTORS].corr()
    correlation.to_csv(OUT / "portfolio_return_correlation.csv")
    print("\nDaily gross portfolio-return correlation:\n", correlation.round(3).to_string())

    figure(returns, summary, correlation, books[COMPOSITE], OUT / "diagnostics.png")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
