"""Single-factor research: IC, quantiles, persistence, turnover and net costs.

Evaluation stops before the sealed 2024-2025 final test. The cutoff is applied
to the *target window*, not to the observation date: the last evaluated date t
is the one whose 20-trading-day forward window still ends on or before the
cutoff, so no return realised in 2024 enters any statistic.

Portfolio convention: equal-weighted long decile 10 / short decile 1, rebuilt on
non-overlapping 20-trading-day rebalance dates so holding periods never overlap.
Weights sum to +1 long and -1 short (gross leverage 2). Turnover is
TO_t = 0.5 * sum_i |w_it - w_i,t-1|, so a full rotation is TO = 2 and the traded
notional is sum_i |dw| = 2 * TO. Costs are charged on traded notional:
net = gross - 2 * c * TO. The first rebalance pays the cost of building the book.

A 20-day rebalance can begin on any of 20 trading-day offsets, and at the
turnover these factors run, that choice moves the result materially. Every
portfolio statistic is therefore the average over all 20 staggered books, and
the spread of gross Sharpe across offsets is reported as sampling uncertainty.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.features.factors import ALL_FACTORS, FACTOR_SIGN, factor_query

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "research_panel"
REPORTS = ROOT / "reports"
CUTOFF = "2023-12-31"      # last date on which a target return may be realised
COSTS_BPS = [1, 5, 10, 20]
REBALANCE_DAYS = 20
PERIODS_PER_YEAR = 252 / REBALANCE_DAYS
OVERLAP_LAG = 20           # daily IC overlap, used for the Newey-West correction


def eligible_query(fac: str, cutoff: str = CUTOFF) -> str:
    """Eligible rows up to the last date whose forward window ends by `cutoff`."""
    return f"""
        SELECT fac.* FROM {fac} AS fac, (
            SELECT MAX(tdi) - {REBALANCE_DAYS} AS last_tdi
            FROM (SELECT DISTINCT tdi, date FROM {fac}) WHERE date <= DATE '{cutoff}'
        ) AS limits
        WHERE fac.eligibility_flag AND fac.tdi <= limits.last_tdi
    """


def cross_section_query(elig: str) -> str:
    """Winsorised, ranked and decile-bucketed cross-section for each date."""
    return f"""
        SELECT permno, date, tdi, f, forward_return_20d AS y,
            LEAST(GREATEST(f, quantile_cont(f, 0.01) OVER d),
                  quantile_cont(f, 0.99) OVER d) AS f_wins,
            (RANK() OVER (PARTITION BY date ORDER BY f) - 1.0)
                / NULLIF(COUNT(*) OVER d - 1, 0) AS f_rank,
            (RANK() OVER (PARTITION BY date ORDER BY forward_return_20d) - 1.0)
                / NULLIF(COUNT(*) OVER d - 1, 0) AS y_rank,
            NTILE(10) OVER (PARTITION BY date ORDER BY f) AS decile,
            COUNT(*) OVER d AS n_used
        FROM {elig}
        WHERE f IS NOT NULL AND forward_return_20d IS NOT NULL
        WINDOW d AS (PARTITION BY date)
    """


def newey_west_tstat(x, lags: int) -> float:
    """t-stat of the mean, robust to the serial correlation caused by overlap."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    e = x - x.mean()
    var = e @ e / n
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * (e[lag:] @ e[:-lag]) / n
    return float(x.mean() / np.sqrt(var / n))


def portfolio(weights: pd.DataFrame) -> pd.DataFrame:
    """Gross/net long-short results from (date, permno, w, y) rebalance weights."""
    w = weights.pivot_table(index="date", columns="permno", values="w", fill_value=0.0)
    gross = weights.assign(pnl=weights.w * weights.y).groupby("date").pnl.sum()
    traded = w.diff().abs().sum(axis=1)
    traded.iloc[0] = w.iloc[0].abs().sum()
    out = pd.DataFrame({"gross_return": gross, "turnover": traded / 2.0})
    for bps in COSTS_BPS:
        out[f"net_return_{bps}bp"] = out.gross_return - (bps / 1e4) * traded
    return out


def performance(returns: pd.Series) -> dict:
    """Annualised stats for a series of non-overlapping 20-day period returns."""
    mean, sd = returns.mean(), returns.std(ddof=1)
    growth = (1 + returns).cumprod()
    # Peak is floored at the starting wealth of 1.0, so a loss before any new
    # high still counts as drawdown.
    peak = growth.cummax().clip(lower=1.0)
    return {
        "mean_period_return": mean,
        "annualised_return": mean * PERIODS_PER_YEAR,
        "annualised_volatility": sd * np.sqrt(PERIODS_PER_YEAR),
        "sharpe": mean / sd * np.sqrt(PERIODS_PER_YEAR),
        "hit_rate": (returns > 0).mean(),
        "max_drawdown": float((growth / peak - 1).min()),
    }


def evaluate(con, source: str, name: str, cutoff: str = CUTOFF) -> dict:
    sign = FACTOR_SIGN[name]
    con.execute(f"CREATE OR REPLACE TEMP TABLE fac AS {factor_query(source, name)}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE elig AS {eligible_query('fac', cutoff)}")
    con.execute(f"CREATE OR REPLACE TEMP TABLE xs AS {cross_section_query('elig')}")

    daily = con.sql("""
        SELECT date, COUNT(*) AS n_eligible, COUNT(f) AS n_factor,
               COUNT(CASE WHEN f IS NOT NULL AND forward_return_20d IS NOT NULL
                          THEN 1 END) AS n_used
        FROM elig GROUP BY date ORDER BY date
    """).df().merge(con.sql("""
        SELECT date, corr(f_wins, y) AS ic_pearson, corr(f_rank, y_rank) AS ic_spearman
        FROM xs GROUP BY date
    """).df(), on="date", how="left")
    daily["coverage"] = daily.n_factor / daily.n_eligible

    # Rank persistence: the same stock's cross-sectional factor rank 1 and 20 days on.
    autocorr = con.sql("""
        SELECT a.date, corr(a.f_rank, b.f_rank) AS rank_autocorr_1d,
               corr(a.f_rank, c.f_rank) AS rank_autocorr_20d
        FROM xs a
        LEFT JOIN xs b ON b.permno = a.permno AND b.tdi = a.tdi + 1
        LEFT JOIN xs c ON c.permno = a.permno AND c.tdi = a.tdi + 20
        GROUP BY a.date ORDER BY a.date
    """).df()

    deciles = con.sql("""
        SELECT decile, AVG(mean_y) AS mean_forward_return_20d,
               STDDEV_SAMP(mean_y) AS sd_across_dates, SUM(n) AS observations
        FROM (SELECT date, decile, AVG(y) AS mean_y, COUNT(*) AS n
              FROM xs GROUP BY date, decile)
        GROUP BY decile ORDER BY decile
    """).df()

    weights = con.sql(f"""
        SELECT tdi, date, permno, y, w FROM (
            SELECT tdi, date, permno, y,
                CASE WHEN decile = 10
                          THEN {sign} * 1.0 / COUNT(*) FILTER (decile = 10) OVER d
                     WHEN decile = 1
                          THEN {-sign} * 1.0 / COUNT(*) FILTER (decile = 1) OVER d
                END AS w
            FROM xs WINDOW d AS (PARTITION BY date)
        ) WHERE w IS NOT NULL
    """).df()
    # A 20-day rebalance can start on any of 20 offsets, and with turnover this
    # high the choice moves the answer. Run all 20 staggered books and report
    # the average, plus the spread across offsets as sampling uncertainty.
    calendar = weights[["tdi", "date"]].drop_duplicates().sort_values("tdi").date
    books = []
    for offset in range(REBALANCE_DAYS):
        dates = set(calendar.iloc[offset::REBALANCE_DAYS])
        books.append(portfolio(weights[weights.date.isin(dates)]).assign(offset=offset))
    columns = ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]
    per_offset = pd.DataFrame([
        {"offset": book.offset.iloc[0], "rebalances": len(book),
         "mean_turnover": book.turnover.mean(),
         **{f"{c}_{k}": v for c in columns for k, v in performance(book[c]).items()}}
        for book in books])

    summary = {
        "factor": name, "hypothesised_sign": sign,
        "first_date": str(daily.date.min().date()),
        "last_date": str(daily.date.max().date()),
        "dates": len(daily), "mean_names_per_date": daily.n_used.mean(),
        "mean_coverage": daily.coverage.mean(), "min_coverage": daily.coverage.min(),
        "mean_ic_pearson": daily.ic_pearson.mean(),
        "sd_ic_pearson": daily.ic_pearson.std(ddof=1),
        "icir_pearson_daily": daily.ic_pearson.mean() / daily.ic_pearson.std(ddof=1),
        "ic_pearson_nw_tstat": newey_west_tstat(daily.ic_pearson, OVERLAP_LAG),
        "mean_ic_spearman": daily.ic_spearman.mean(),
        "sd_ic_spearman": daily.ic_spearman.std(ddof=1),
        "icir_spearman_daily": daily.ic_spearman.mean() / daily.ic_spearman.std(ddof=1),
        "ic_spearman_nw_tstat": newey_west_tstat(daily.ic_spearman, OVERLAP_LAG),
        "share_ic_spearman_positive": (daily.ic_spearman > 0).mean(),
        "mean_rank_autocorr_1d": autocorr.rank_autocorr_1d.mean(),
        "mean_rank_autocorr_20d": autocorr.rank_autocorr_20d.mean(),
        "mean_ic_spearman_signed": sign * daily.ic_spearman.mean(),
        "decile_spread_20d": (deciles.mean_forward_return_20d.iloc[-1]
                              - deciles.mean_forward_return_20d.iloc[0]),
        "decile_spread_signed": sign * (deciles.mean_forward_return_20d.iloc[-1]
                                        - deciles.mean_forward_return_20d.iloc[0]),
    }
    # Portfolio statistics are averaged over the 20 rebalance offsets.
    summary.update(per_offset.drop(columns="offset").mean().to_dict())
    summary["gross_return_sharpe_sd_across_offsets"] = \
        per_offset.gross_return_sharpe.std(ddof=1)
    summary["gross_return_sharpe_min_offset"] = per_offset.gross_return_sharpe.min()
    summary["gross_return_sharpe_max_offset"] = per_offset.gross_return_sharpe.max()

    yearly = daily.assign(year=daily.date.dt.year).groupby("year").agg(
        dates=("date", "size"), mean_names=("n_used", "mean"),
        ic_pearson=("ic_pearson", "mean"), ic_spearman=("ic_spearman", "mean"),
        icir_spearman=("ic_spearman", lambda s: s.mean() / s.std(ddof=1)),
    ).reset_index()

    return {"daily": daily.merge(autocorr, on="date", how="left"), "deciles": deciles,
            "portfolio": pd.concat(books).reset_index(), "offsets": per_offset,
            "yearly": yearly,
            "summary": pd.DataFrame([summary]).T.rename(columns={0: "value"})}


def figure(name: str, out: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    daily = out["daily"].set_index("date")
    book = out["portfolio"].query("offset == 0").set_index("date")
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    daily.ic_spearman.rolling(252).mean().plot(ax=ax[0, 0])
    ax[0, 0].axhline(0, color="k", lw=0.8)
    ax[0, 0].set_title("Rolling 252-day mean rank IC")
    ax[0, 1].hist(daily.ic_spearman.dropna(), bins=60)
    ax[0, 1].axvline(daily.ic_spearman.mean(), color="r")
    ax[0, 1].set_title("Daily rank IC distribution")
    ax[1, 0].bar(out["deciles"].decile, out["deciles"].mean_forward_return_20d)
    ax[1, 0].set_title("Mean 20-day forward return by factor decile")
    for column in ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]:
        (1 + book[column]).cumprod().plot(ax=ax[1, 1], label=column, logy=True)
    ax[1, 1].legend(fontsize=7)
    ax[1, 1].set_title("Long-short cumulative growth (rebalance offset 0 of 20)")
    fig.suptitle(f"{name}: {out['summary'].loc['first_date', 'value']} to "
                 f"{out['summary'].loc['last_date', 'value']}")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    import duckdb

    names = sys.argv[1:] or ALL_FACTORS
    if not PANEL.exists():
        sys.exit("Research panel not found. Run src/data/build_research_panel.py first.")
    con = duckdb.connect()
    source = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    summaries = []
    for name in names:
        outdir = REPORTS / f"factor_{name}"
        outdir.mkdir(parents=True, exist_ok=True)
        out = evaluate(con, source, name)
        for key, frame in out.items():
            frame.to_csv(outdir / f"{key}.csv", index=(key == "summary"))
        figure(name, out, outdir / "diagnostics.png")
        summaries.append(out["summary"].rename(columns={"value": name}))
        print(out["summary"].to_string(), "\n\nWrote", outdir, "\n", flush=True)
    combined = pd.concat(summaries, axis=1)
    combined.to_csv(REPORTS / "factor_summary.csv")
    print(combined.to_string())


if __name__ == "__main__":
    main()
