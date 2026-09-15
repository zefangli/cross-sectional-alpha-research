"""Single-factor research: IC, quantiles, persistence, turnover and net costs.

Evaluation stops before the sealed 2024-2025 final test. The cutoff is applied
to the *target window*, not to the observation date: the last evaluated date t
is the one whose 20-trading-day forward window still ends on or before the
cutoff, so no return realised in 2024 enters any statistic.

Portfolio convention: equal-weighted long decile 10 / short decile 1, rebuilt on
non-overlapping 20-trading-day rebalance dates so holding periods never overlap.
Weights sum to +1 long and -1 short (gross leverage 2). Traded notional at a
rebalance is sum_i |w_it - h_i,t-1| where h is the previous book drifted by its
own period return (see `portfolio`), TO_t = traded / 2, and costs are charged on
traded notional: net = gross - c * traded. The first rebalance pays the cost of
building the book.

Formation and evaluation are separated (2026-09-14 review, items 2 and 5):
ranks, deciles and weights are formed from every eligible row with a factor
value, whether or not its 20-day target turns out to be observable; the
information coefficient is a labelled diagnostic over complete (factor, target)
pairs, ranked with average ranks so ties match `scipy.stats.spearmanr`. A held
name is marked with `forward_return_20d_observed` -- whatever the panel observed
in the next 20 trading days, delisting return included -- so a name whose data
end mid-window keeps its known returns and accrues 0 only for the unobserved
remainder (2026-09-15 follow-up, item 2). Names whose complete 20-day label is
missing are counted in `names_without_target`; those with no observation at all
accrue 0 and are counted in `names_without_any_return`.

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


def average_rank_query(table: str, by: str, x: str, y: str) -> str:
    """Complete (x, y) pairs within each `by` group, with average ranks
    (`scipy.stats.rankdata(method='average')`) as `x_rank` and `y_rank`.

    Rows where either side is NULL are dropped BEFORE ranking, so a missing
    target can never occupy a rank. Ties get the mean of the positions they
    span, which SQL `RANK()` (competition ranks) does not give.
    """
    return f"""
        WITH paired AS (
            SELECT {by}, {x} AS x, {y} AS y FROM {table}
            WHERE {x} IS NOT NULL AND {y} IS NOT NULL
        ), numbered AS (
            SELECT {by}, x, y,
                ROW_NUMBER() OVER (PARTITION BY {by} ORDER BY x, y) AS x_ord,
                ROW_NUMBER() OVER (PARTITION BY {by} ORDER BY y, x) AS y_ord
            FROM paired
        )
        SELECT {by}, x, y,
            AVG(x_ord) OVER (PARTITION BY {by}, x) AS x_rank,
            AVG(y_ord) OVER (PARTITION BY {by}, y) AS y_rank
        FROM numbered
    """


def spearman_query(table: str, by: str, x: str, y: str) -> str:
    """Spearman correlation of `x` and `y` per `by` group, complete pairs only."""
    return f"""
        SELECT {by}, corr(x_rank, y_rank) AS ic_spearman
        FROM ({average_rank_query(table, by, x, y)}) GROUP BY {by}
    """


def cross_section_query(elig: str, observed: bool = False) -> str:
    """Winsorised, ranked and decile-bucketed formation cross-section per date.

    Every eligible row with a factor value is formed on; `y` (the complete
    label) and `y_obs` (the observed-window marking return, when the source
    carries it) are carried along, possibly NULL, and never condition
    membership.
    """
    return f"""
        SELECT permno, date, tdi, f, forward_return_20d AS y,
            {'forward_return_20d_observed' if observed else 'forward_return_20d'} AS y_obs,
            LEAST(GREATEST(f, quantile_cont(f, 0.01) OVER d),
                  quantile_cont(f, 0.99) OVER d) AS f_wins,
            (RANK() OVER (PARTITION BY date ORDER BY f) - 1.0)
                / NULLIF(COUNT(*) OVER d - 1, 0) AS f_rank,
            NTILE(10) OVER (PARTITION BY date ORDER BY f) AS decile,
            COUNT(*) OVER d AS n_formed
        FROM {elig}
        WHERE f IS NOT NULL
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
    """Gross/net long-short results from (date, permno, w, y) rebalance weights.

    Traded notional at each rebalance is |w_t - h_{t-1}| summed over names,
    where h_{t-1} is the previous book after its own period return, as a
    fraction of the grown NAV: h = w_{t-1}(1 + y_{t-1}) / (1 + gross_{t-1}).
    `y` is the marking return (observed window); a NULL `y` accrues 0 and
    drifts as 0. An optional `y_label` column (the complete 20-day target) is
    only counted, never used for P&L.
    """
    w = weights.pivot_table(index="date", columns="permno", values="w", fill_value=0.0)
    y = weights.pivot_table(index="date", columns="permno", values="y", fill_value=0.0) \
        .reindex(index=w.index, columns=w.columns, fill_value=0.0)
    gross = (w * y).sum(axis=1)
    held = (w * (1 + y)).div(1 + gross, axis=0).shift(1).fillna(0.0)
    traded = (w - held).abs().sum(axis=1)
    label = weights["y_label"] if "y_label" in weights else weights.y
    out = pd.DataFrame({
        "gross_return": gross, "turnover": traded / 2.0,
        "names_without_target": label.isna().groupby(weights.date).sum().reindex(w.index),
        "names_without_any_return": weights.y.isna().groupby(weights.date).sum().reindex(w.index),
    })
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
    # The observed-window marking return rides alongside the factor rows; it is
    # not a factor input, so it is joined back from the panel rather than
    # threaded through `factor_query`.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE elig AS
        SELECT e.*, s.forward_return_20d_observed
        FROM ({eligible_query('fac', cutoff)}) e
        JOIN {source} s USING (permno, date)
    """)
    con.execute(f"CREATE OR REPLACE TEMP TABLE xs AS {cross_section_query('elig', observed=True)}")

    # IC is a labelled diagnostic over complete (factor, target) pairs; n_used
    # counts those pairs, n_formed the formation universe they sit inside.
    daily = con.sql("""
        SELECT date, COUNT(*) AS n_eligible, COUNT(f) AS n_factor,
               COUNT(CASE WHEN f IS NOT NULL AND forward_return_20d IS NOT NULL
                          THEN 1 END) AS n_used
        FROM elig GROUP BY date ORDER BY date
    """).df().merge(con.sql("""
        SELECT date, corr(f_wins, y) AS ic_pearson FROM xs GROUP BY date
    """).df(), on="date", how="left").merge(
        con.sql(spearman_query("xs", "date", "f", "y")).df(), on="date", how="left")
    daily["coverage"] = daily.n_factor / daily.n_eligible
    daily["target_coverage"] = daily.n_used / daily.n_factor

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
        SELECT tdi, date, permno, y_obs AS y, y AS y_label, w FROM (
            SELECT tdi, date, permno, y, y_obs,
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
         "mean_names_without_target": book.names_without_target.mean(),
         "mean_names_without_any_return": book.names_without_any_return.mean(),
         **{f"{c}_{k}": v for c in columns for k, v in performance(book[c]).items()}}
        for book in books])

    summary = {
        "factor": name, "hypothesised_sign": sign,
        "first_date": str(daily.date.min().date()),
        "last_date": str(daily.date.max().date()),
        "dates": len(daily), "mean_names_per_date": daily.n_factor.mean(),
        "mean_complete_pairs_per_date": daily.n_used.mean(),
        "mean_coverage": daily.coverage.mean(), "min_coverage": daily.coverage.min(),
        "mean_target_coverage": daily.target_coverage.mean(),
        "min_target_coverage": daily.target_coverage.min(),
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


def factor_names(argv: list, names=None) -> list:
    """Explicit `names` win; otherwise positional CLI arguments; otherwise all.
    A caller embedding this module (the correction runner) passes `names`
    explicitly so a foreign flag such as `--from-step` on `sys.argv` is never
    mistaken for a factor (2026-09-15 follow-up, item 4)."""
    if names is not None:
        return list(names)
    unknown = [a for a in argv if not a.startswith("-") and a not in ALL_FACTORS]
    if unknown and not any(a.startswith("-") for a in argv):
        raise SystemExit(f"unknown factor name(s) {unknown}; choose from {ALL_FACTORS}")
    positional = [a for a in argv if a in ALL_FACTORS]
    return positional or list(ALL_FACTORS)


def main(names=None) -> None:
    import duckdb

    names = factor_names(sys.argv[1:], names)
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
