"""Week 4: OLS, Ridge and gradient boosting evaluated against the Week 3 baseline.

Consumes `data/processed/week4_predictions.parquet` (built by
`src/models/walk_forward.py`) and does two things with it: measures raw
prediction quality against `forward_return_20d`, and forms portfolios through
the unmodified Week 3 backtest (`src/portfolio/backtest.py`).

OOS R^2 is benchmarked against the TRAINING-period mean target, not the
validation mean. The validation mean would leak the validation period's own
realised average return into the "no-skill" prediction, inflating R^2 for any
model that predicts close to a constant.

Portfolio mechanics, per fold: the signal frame is that fold's rows in the
predictions parquet, warm-up (`is_validation=False`) included. Cohorts are
formed on every date in that frame, so the 20 staggered cohorts are already
fully ramped by the fold's first validation day -- this requires calling
`daily_book` with `first_date` set to the warm-up start, not the validation
start, because its rolling 20-day weight window can only sum over dates
present in its own date-filtered grid. The returned daily frame is then
truncated to [validation_start, validation_end] before use, which is what
actually keeps P&L marking confined to the validation window and the ten
per-fold frames non-overlapping when concatenated.

The Week 3 equal-weighted signed-rank composite is recomputed through this
identical per-fold machinery -- same fold dates, same warm-up, same
`capped_neutral_weights` call, same decile threshold -- so the comparison
against the fitted models is apples-to-apples on 2014-2023 only. The Week 3
memo's 2006-2023 headline (gross Sharpe 0.121 rank / 0.147 decile) is a
different, longer sample and is not the comparison bar here.

2024-2025 stays sealed: every fold's dates are capped at COHORT_LAST, imported
from `walk_forward.py` so the two modules can never disagree about the cutoff.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.evaluation.factor_eval import newey_west_tstat, OVERLAP_LAG
from src.evaluation.week3_baseline import COMPOSITE
from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.models.splits import walk_forward_splits
from src.models.walk_forward import COHORT_LAST, MODELS, PREDICTIONS, TARGET, WARMUP_DAYS
from src.portfolio.backtest import (CAP, COSTS_BPS, TRADING_DAYS,
                                     capped_neutral_weights, daily_book, performance_daily)

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
OUT = ROOT / "reports" / "week4"
PNL_LAST = "2023-12-31"
NAMES = list(MODELS) + [COMPOSITE]


def train_means(con, scan: str, splits: pd.DataFrame) -> pd.DataFrame:
    """Training-period mean target per fold -- the R^2 benchmark, not the fold's own."""
    rows = [{"fold": int(f.fold), "train_mean": con.sql(f"""
                SELECT AVG({TARGET}) FROM {scan}
                WHERE aligned AND date <= DATE '{f.train_end}' AND {TARGET} IS NOT NULL
            """).fetchone()[0]}
            for f in splits.itertuples()]
    return pd.DataFrame(rows)


def prediction_quality(con, scan: str, predictions: pd.DataFrame, splits: pd.DataFrame) -> tuple:
    """Per-fold and pooled MSE/MAE/OOS R^2 and daily cross-sectional IC, on validation rows.

    Pearson IC is `corr(prediction, y)`; Spearman is Pearson correlation of the
    two within-date percentile ranks, the same construction `factor_eval.py`
    uses. Both are averaged into a daily series and given a Newey-West t-stat
    at `OVERLAP_LAG` lags, since the shared 20-day target makes adjacent days
    overlap.
    """
    con.register("predictions", predictions.loc[predictions.is_validation,
                 ["permno", "date", "tdi", "fold", "model", "prediction"]])
    con.register("train_means", train_means(con, scan, splits))
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE joined AS
        SELECT p.date, p.fold, p.model, p.prediction, f.{TARGET} AS y, m.train_mean
        FROM predictions p
        JOIN {scan} f USING (permno, tdi)
        JOIN train_means m USING (fold)
    """)
    con.unregister("predictions")
    con.unregister("train_means")

    error_sql = """
        SELECT {by}, COUNT(*) AS validation_rows,
            AVG(POWER(prediction - y, 2)) AS mse, AVG(ABS(prediction - y)) AS mae,
            1 - SUM(POWER(prediction - y, 2)) / SUM(POWER(y - train_mean, 2)) AS r2_oos
        FROM joined GROUP BY {by}
    """
    error_fold = con.sql(error_sql.format(by="fold, model")).df()
    error_pooled = con.sql(error_sql.format(by="model")).df()

    daily = con.sql("""
        WITH ranked AS (
            SELECT *,
                (RANK() OVER (PARTITION BY date, model ORDER BY prediction) - 1.0)
                    / NULLIF(COUNT(*) OVER (PARTITION BY date, model) - 1, 0) AS pred_rank,
                (RANK() OVER (PARTITION BY date, model ORDER BY y) - 1.0)
                    / NULLIF(COUNT(*) OVER (PARTITION BY date, model) - 1, 0) AS y_rank
            FROM joined
        )
        SELECT date, fold, model,
            corr(prediction, y) AS ic_pearson, corr(pred_rank, y_rank) AS ic_spearman
        FROM ranked GROUP BY date, fold, model
    """).df()

    def ic_agg(group_cols):
        return daily.groupby(group_cols).agg(
            mean_ic_pearson=("ic_pearson", "mean"),
            ic_pearson_nw_tstat=("ic_pearson", lambda s: newey_west_tstat(s, OVERLAP_LAG)),
            mean_ic_spearman=("ic_spearman", "mean"),
            ic_spearman_nw_tstat=("ic_spearman", lambda s: newey_west_tstat(s, OVERLAP_LAG)),
        ).reset_index()

    fold_metrics = error_fold.merge(ic_agg(["fold", "model"]), on=["fold", "model"])
    model_metrics = error_pooled.merge(ic_agg(["model"]), on="model")
    return fold_metrics, model_metrics


def composite_frame(con, scan: str, fold) -> pd.DataFrame:
    """This fold's (permno, date, tdi, rank_<factor>) rows, warm-up included.

    Mirrors the tdi arithmetic `walk_forward.fold_frames` uses for its PREDICT
    block -- same WARMUP_DAYS constant, same validation window -- without
    paying for that function's TRAIN query, which this composite never needs.
    """
    columns = ", ".join(f"rank_{f}" for f in ALL_FACTORS)
    validation_end = min(pd.Timestamp(fold.validation_end), pd.Timestamp(COHORT_LAST))
    return con.sql(f"""
        SELECT permno, date, tdi, {columns}
        FROM {scan}
        WHERE aligned
          AND tdi >= (SELECT tdi FROM {scan} WHERE date = DATE '{fold.validation_start}'
                      LIMIT 1) - {WARMUP_DAYS}
          AND date <= DATE '{validation_end.date()}'
        ORDER BY tdi
    """).df()


def book_frame(con, scan: str, fold, name: str, predictions: pd.DataFrame) -> pd.DataFrame:
    """This fold's signal frame for `name`, with both a `rank` and a `decile` column.

    `rank` is the equal-weighted signed-rank composite itself for the Week 3
    baseline (unchanged from `week3_baseline.py`, so that book is a faithful
    recomputation), or the cross-sectional percentile rank of `prediction` for
    a fitted model. `decile` is a further per-date percentile-rank-and-threshold
    of `rank`, identical code for both: a no-op re-rank for the models, and the
    same construction `week3_baseline.py` used for `decile_composite`.
    """
    if name == COMPOSITE:
        frame = composite_frame(con, scan, fold)
        frame["rank"] = sum(FACTOR_SIGN[f] * frame[f"rank_{f}"] for f in ALL_FACTORS) / len(ALL_FACTORS)
    else:
        frame = predictions.loc[(predictions.fold == fold.fold) & (predictions.model == name),
                                 ["permno", "date", "tdi", "prediction"]].copy()
        frame["rank"] = frame.groupby("date")["prediction"].rank(pct=True)
    pct = frame.groupby("date")["rank"].rank(pct=True)
    frame["decile"] = np.where(pct >= 0.9, 1.0, np.where(pct <= 0.1, -1.0, 0.0))
    return frame


def fold_book(con, scan: str, fold, frame: pd.DataFrame, weighting: str) -> pd.DataFrame:
    """Form cohorts over the whole fold frame, mark P&L only inside the validation window."""
    cohort = frame[["permno", "tdi", "date"]].copy()
    cohort["w"] = capped_neutral_weights(frame, weighting)
    con.register("cohort", cohort[["permno", "tdi", "w"]])
    warmup_start = str(frame.date.min().date())
    validation_end = str(min(pd.Timestamp(fold.validation_end), pd.Timestamp(COHORT_LAST)).date())
    daily = daily_book(con, scan, warmup_start, validation_end, factors=ALL_FACTORS)
    con.unregister("cohort")
    return daily[daily.date >= pd.Timestamp(fold.validation_start)]


def summarize(daily: pd.DataFrame) -> dict:
    """Book statistics, mirroring `backtest.run`'s summary block over a concatenated frame."""
    summary = {
        "days": len(daily),
        "first_date": str(daily.date.min().date()), "last_date": str(daily.date.max().date()),
        "mean_positions": daily.positions.mean(),
        "mean_gross_exposure": daily.gross_exposure.mean(),
        "mean_net_exposure": daily.net_exposure.mean(),
        "max_abs_net_exposure": daily.net_exposure.abs().max(),
        "largest_position": daily.max_abs_weight.max(),
        "cap": CAP, "cap_binds": bool(daily.max_abs_weight.max() > CAP - 1e-9),
        "mean_daily_turnover": daily.turnover.mean(),
        "annual_turnover_multiple": daily.turnover.mean() * TRADING_DAYS,
        "positions_without_return_per_day": daily.positions_without_return.mean(),
        "breakeven_bp": 1e4 * daily.gross_return.mean() / daily.traded.mean(),
    }
    for column in ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]:
        for key, value in performance_daily(daily[column], daily.market_return).items():
            summary[f"{column}_{key}"] = value
    for factor in ALL_FACTORS:
        summary[f"exposure_{factor}"] = daily[f"exposure_{factor}"].mean()
    return summary


def figure(books: dict, summary: pd.DataFrame, fold_metrics: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    colors = dict(zip(NAMES, plt.rcParams["axes.prop_cycle"].by_key()["color"]))

    returns = pd.DataFrame({label: daily.set_index("date").gross_return
                            for label, daily in books.items()})
    cumulative = (1 + returns).cumprod()
    for label in cumulative.columns:
        base = label.split("__")[0]
        ax[0, 0].plot(cumulative.index, cumulative[label], lw=1, color=colors[base],
                      linestyle="--" if label.endswith("__decile") else "-", label=label)
    ax[0, 0].set_title("Cumulative out-of-sample gross return, 2014-2023")
    ax[0, 0].legend(fontsize=6, ncol=2)

    costs = [0] + COSTS_BPS
    for label in returns.columns:
        base = label.split("__")[0]
        sharpes = [summary.loc["gross_return_sharpe", label]] + [
            summary.loc[f"net_return_{b}bp_sharpe", label] for b in COSTS_BPS]
        ax[0, 1].plot(costs, sharpes, marker="o", ms=3, color=colors[base],
                      linestyle="--" if label.endswith("__decile") else "-", label=label)
    ax[0, 1].axhline(0, color="k", lw=0.8)
    ax[0, 1].set_xlabel("cost, bp of traded notional")
    ax[0, 1].set_title("Sharpe versus assumed cost")
    ax[0, 1].legend(fontsize=6, ncol=2)

    ic = fold_metrics.pivot(index="fold", columns="model", values="mean_ic_spearman")[list(MODELS)]
    x = np.arange(len(ic.index))
    width = 0.8 / len(MODELS)
    for i, model in enumerate(MODELS):
        ax[1, 0].bar(x + (i - (len(MODELS) - 1) / 2) * width, ic[model], width, label=model)
    ax[1, 0].axhline(0, color="k", lw=0.8)
    ax[1, 0].set_xticks(x, ic.index)
    ax[1, 0].set_xlabel("fold")
    ax[1, 0].set_title("Per-fold mean rank IC by model")
    ax[1, 0].legend(fontsize=7)

    exposures = summary.loc[[f"exposure_{f}" for f in ALL_FACTORS], list(MODELS)]
    x = np.arange(len(ALL_FACTORS))
    for i, model in enumerate(MODELS):
        ax[1, 1].bar(x + (i - (len(MODELS) - 1) / 2) * width, exposures[model].values, width, label=model)
    ax[1, 1].axhline(0, color="k", lw=0.8)
    ax[1, 1].set_xticks(x, ALL_FACTORS, rotation=45, ha="right", fontsize=7)
    ax[1, 1].set_title("Mean factor exposure by model (rank-weighted book)")
    ax[1, 1].legend(fontsize=7)

    fig.suptitle("Week 4: fitted models versus the Week 3 baseline, 2014-2023 out of sample")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    if not PREDICTIONS.exists():
        sys.exit("Week 4 predictions not found. Run src/models/walk_forward.py first.")
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"

    predictions = pd.read_parquet(PREDICTIONS)
    assert predictions.date.max() <= pd.Timestamp(COHORT_LAST), "prediction past the sealed period"

    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)

    # 1. Prediction quality on validation rows only.
    fold_metrics, model_metrics = prediction_quality(con, scan, predictions, splits)
    fold_metrics.to_csv(OUT / "fold_metrics.csv", index=False)
    model_metrics.to_csv(OUT / "model_metrics.csv", index=False)
    print("Per-fold mean rank IC by model:\n",
          fold_metrics.pivot(index="fold", columns="model", values="mean_ic_spearman")
          .round(4).to_string(), "\n")
    print("Pooled model metrics:\n", model_metrics.round(4).to_string(index=False), "\n")

    # 2. Portfolios: three fitted models plus the recomputed Week 3 composite,
    # each under rank and decile weighting, through the identical fold machinery.
    books = {}
    for name in NAMES:
        frames = {int(f.fold): book_frame(con, scan, f, name, predictions) for f in splits.itertuples()}
        for weighting in ("rank", "decile"):
            label = name if weighting == "rank" else f"{name}__decile"
            parts = [fold_book(con, scan, f, frames[int(f.fold)], weighting) for f in splits.itertuples()]
            daily = pd.concat(parts, ignore_index=True).sort_values("date").reset_index(drop=True)
            assert daily.date.is_monotonic_increasing, f"{label}: dates out of order"
            assert not daily.date.duplicated().any(), f"{label}: duplicate dates across fold boundaries"
            assert daily.date.max() <= pd.Timestamp(PNL_LAST), f"{label}: P&L marked past 2023"
            books[label] = daily
            daily.to_csv(OUT / f"daily_{label}.csv", index=False)
            print(f"{label:18s} days {len(daily):5d}  "
                  f"{daily.date.min().date()} -> {daily.date.max().date()}", flush=True)

    n_days = len(next(iter(books.values())))
    assert all(len(daily) == n_days for daily in books.values()), "books disagree on day count"
    assert 2400 <= n_days <= 2600, f"unexpected out-of-sample day count: {n_days}"

    summary = pd.concat([pd.Series(summarize(daily), name=label)
                         for label, daily in books.items()], axis=1)
    summary.to_csv(OUT / "portfolio_summary.csv")

    comparison = pd.DataFrame([{
        "book": label,
        "gross_sharpe": summary.loc["gross_return_sharpe", label],
        "net_sharpe_10bp": summary.loc["net_return_10bp_sharpe", label],
        "breakeven_bp": summary.loc["breakeven_bp", label],
        "annual_turnover": summary.loc["annual_turnover_multiple", label],
        "beta": summary.loc["gross_return_market_beta", label],
        "max_drawdown": summary.loc["gross_return_max_drawdown", label],
    } for label in books]).sort_values("net_sharpe_10bp", ascending=False)
    comparison.to_csv(OUT / "model_comparison.csv", index=False)

    print(f"\nOut-of-sample daily series: {n_days} trading days, "
          f"{next(iter(books.values())).date.min().date()} -> "
          f"{next(iter(books.values())).date.max().date()}\n")
    print("Model comparison (sorted by net Sharpe at 10bp):\n",
          comparison.round(4).to_string(index=False))

    figure(books, summary, fold_metrics, OUT / "diagnostics.png")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
