"""Final-report figures for the Week 6 sealed test.

The research is finished: the locked book `drop_rmom_120_20__neutral__decile`
ran once against 2024-2025 and the result is fixed (`reports/week6_final_memo.md`).
Nothing here fits, tunes or tests anything -- every number plotted is a column
already sitting in `reports/week5/*.csv` or `reports/week6/*.csv`, summarised
with the same operations Weeks 3-5 already used (cumulative product, rolling
mean/cov/var, plain means). The only editorial judgement is layout, and the
one rule threaded through every panel: a figure spanning both periods must
never look like one continuous backtest, because the selection sample was
used to *choose* this book and the sealed period was not.
"""
from pathlib import Path
from typing import Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
W5 = ROOT / "reports" / "week5"
W6 = ROOT / "reports" / "week6"
OUT = ROOT / "reports" / "figures"

LOCKED = "drop_rmom_120_20__neutral__decile"
SEAL_DATE = pd.Timestamp("2024-01-03")
COSTS = [0, 1, 5, 10, 20]
FACTORS = ["mom_120_20", "rev_5", "rvol_20", "vs_20", "rmom_120_20", "dd_252"]
CONTROLS = ["beta_252", "log_mcap", "sector"]
SECTOR_COLS = [f"exposure_sector_{s}" for s in range(11)]

SELECTION = "selection sample (2014-2023, used to choose this book)"
SEALED = "sealed test (2024-2025, evaluated once)"
GREY, BLACK = "0.55", "0.0"


def load() -> Tuple[pd.DataFrame, pd.DataFrame]:
    sel = pd.read_csv(W5 / f"daily_{LOCKED}.csv", parse_dates=["date"])
    sea = pd.read_csv(W6 / "final_daily.csv", parse_dates=["date"])
    return sel, sea


def sharpe(returns: pd.Series) -> float:
    return returns.mean() / returns.std(ddof=1) * np.sqrt(252)


def fig_cumulative(sel, sea, path) -> None:
    """Headline: cumulative return rebased to 1.0 at the start of each period
    separately, plotted on one calendar axis -- a shared axis without
    chaining the two periods multiplicatively, so the picture cannot be read
    as one uninterrupted equity curve."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for df, label, color in [(sel, SELECTION, GREY), (sea, SEALED, BLACK)]:
        (1 + df.set_index("date").gross_return).cumprod().plot(
            ax=ax, color=color, lw=1.2, ls="-", label=f"{label}: gross")
        (1 + df.set_index("date").net_return_10bp).cumprod().plot(
            ax=ax, color=color, lw=1.2, ls="--", label=f"{label}: net @10bp")
    ax.axvline(SEAL_DATE, color="k", lw=1, ls=":")
    ax.axvspan(SEAL_DATE, sea.date.max(), color="0.92", zorder=0)
    ax.text(SEAL_DATE, ax.get_ylim()[1], "  seal opens 2024-01-03", va="top", fontsize=8)
    ax.set_ylabel("cumulative growth of $1 (rebased to 1.0 at period start)")
    ax.set_title("Cumulative return: selection sample vs. sealed test\n"
                  "(two separate curves, not a chained track record -- the book was chosen using the left side)")
    ax.legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def fig_sharpe_vs_cost(sel, sea, path) -> None:
    """Sharpe at each modelled cost tier, both periods, with the breakeven
    (Sharpe = 0 crossing) marked at the values already reported: 18.0bp
    selection, 49.7bp sealed."""
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    for df, label, color, breakeven in [(sel, SELECTION, GREY, 18.028461),
                                         (sea, SEALED, BLACK, 49.66280)]:
        cols = ["gross_return"] + [f"net_return_{b}bp" for b in COSTS[1:]]
        sharpes = [sharpe(df[c].dropna()) for c in cols]
        ax.plot(COSTS, sharpes, marker="o", ms=4, color=color, label=label)
        ax.axvline(breakeven, color=color, lw=0.8, ls=":")
        ax.annotate(f"breakeven {breakeven:.1f}bp", (breakeven, 0),
                    textcoords="offset points", xytext=(4, 6), fontsize=7, color=color)
    ax.set_ylim(top=3.3)
    ax.axhline(0, color="k", lw=0.8)
    ax.errorbar([1], [1.5216], yerr=[[1.5216 - 0.44], [2.60 - 1.5216]],
                fmt="none", ecolor="k", elinewidth=1, capsize=4)
    ax.annotate("sealed gross Sharpe 1.52\nprimary HAC 95% CI [0.44, 2.60]", (1, 2.60),
                textcoords="offset points", xytext=(6, 2), fontsize=7)
    ax.set_xlabel("assumed cost, bp of traded notional")
    ax.set_ylabel("annualised Sharpe")
    ax.set_title("Sharpe versus assumed cost, selection sample vs. sealed test")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def fig_rolling_beta(sel, sea, path) -> None:
    """Rolling 252-day market beta, computed independently within each
    period (the window is not allowed to straddle the seal), against the
    +/-0.10 band the selection rule imposed on the selection sample only."""
    fig, ax = plt.subplots(figsize=(9, 4))
    for df, label, color in [(sel, SELECTION, GREY), (sea, SEALED, BLACK)]:
        d = df.set_index("date")
        beta = d.gross_return.rolling(252).cov(d.market_return) / d.market_return.rolling(252).var()
        beta.plot(ax=ax, color=color, lw=1, label=label)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhspan(-0.10, 0.10, color="0.85", zorder=0, label="|beta| <= 0.10 selection constraint")
    ax.axvline(SEAL_DATE, color="k", lw=1, ls=":")
    ax.set_ylabel("rolling 252-day market beta")
    ax.set_ylim(-0.20, 0.20)
    ax.set_title("Rolling market beta stayed inside the selection constraint out of sample")
    ax.legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def fig_exposures(sel, sea, path) -> None:
    """Mean factor/control exposures, selection sample vs. sealed period.
    `exposure_sector` follows the exact aggregation `week5_neutral.summarize`
    uses: mean-over-days of the sum of |net sector weight| across sectors."""
    def means(df):
        out = {f: df[f"exposure_{f}"].mean() for f in FACTORS + ["beta_252", "log_mcap"]}
        out["sector"] = sum(df[c].abs().mean() for c in SECTOR_COLS)
        return out

    labels = FACTORS + CONTROLS
    m_sel, m_sea = means(sel), means(sea)
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x - width / 2, [m_sel[l] for l in labels], width, color=GREY, label=SELECTION)
    ax.bar(x + width / 2, [m_sea[l] for l in labels], width, color=BLACK, label=SEALED)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x, labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("mean exposure")
    ax.set_title(f"Factor exposures, selection sample vs. sealed test\n"
                 f"(rmom_120_20 dropped from the inputs, still carries {m_sea['rmom_120_20']:.3f} exposure out of sample)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def fig_candidate_grid(path) -> None:
    """All 40 selection-sample candidates: net Sharpe at 10bp vs. realised
    beta, the |beta|<=0.10 admissibility band, and the locked winner. Shows
    the selection rule doing its work and the size of the field it was
    chosen from."""
    cand = pd.read_csv(W5 / "candidates.csv")
    admissible = cand.realised_beta.abs() <= 0.10
    winner = cand.book == LOCKED

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.axvspan(-0.10, 0.10, color="0.9", zorder=0, label="|beta| <= 0.10 (admissible)")
    ax.scatter(cand.loc[~admissible, "realised_beta"], cand.loc[~admissible, "net_sharpe_10bp"],
               marker="x", color=GREY, label="inadmissible (20)")
    ax.scatter(cand.loc[admissible & ~winner, "realised_beta"], cand.loc[admissible & ~winner, "net_sharpe_10bp"],
               marker="o", facecolors="none", edgecolors=BLACK, label="admissible (20)")
    ax.scatter(cand.loc[winner, "realised_beta"], cand.loc[winner, "net_sharpe_10bp"],
               marker="*", s=220, color=BLACK, label="locked winner", zorder=5)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("realised market beta, selection sample")
    ax.set_ylabel("net Sharpe at 10bp, selection sample")
    ax.set_title("The 40-book candidate grid: selection-sample Sharpe vs. realised beta\n"
                 "(the locked book is the best of 20 admissible, correlated candidates)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def fig_drawdown(sel, sea, path) -> None:
    """Drawdown of gross return, each period computed against its own
    running peak (no cross-boundary peak-carry, same reasoning as figure 1)."""
    fig, ax = plt.subplots(figsize=(9, 3.5))
    for df, label, color in [(sel, SELECTION, GREY), (sea, SEALED, BLACK)]:
        growth = (1 + df.set_index("date").gross_return).cumprod()
        dd = growth / growth.cummax() - 1
        dd.plot(ax=ax, color=color, lw=1, label=label)
    ax.axvline(SEAL_DATE, color="k", lw=1, ls=":")
    ax.axvspan(SEAL_DATE, sea.date.max(), color="0.92", zorder=0)
    ax.set_ylabel("drawdown from period-own peak")
    ax.set_title("Gross drawdown, selection sample vs. sealed test")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sel, sea = load()
    assert sel.date.max() < SEAL_DATE <= sea.date.min()

    fig_cumulative(sel, sea, OUT / "01_cumulative_return.png")
    fig_sharpe_vs_cost(sel, sea, OUT / "02_sharpe_vs_cost.png")
    fig_rolling_beta(sel, sea, OUT / "03_rolling_beta.png")
    fig_exposures(sel, sea, OUT / "04_factor_exposures.png")
    fig_candidate_grid(OUT / "05_candidate_grid.png")
    fig_drawdown(sel, sea, OUT / "06_drawdown.png")
    print(f"Wrote 6 figures to {OUT}")


if __name__ == "__main__":
    main()
