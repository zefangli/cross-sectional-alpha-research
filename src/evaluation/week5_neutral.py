"""W5-003: cross-sectional neutralisation of the composite and the three models
against sector, beta_252 and log_mcap, run through the unchanged Week 4 book.

Every score -- the equal-weighted signed-rank composite and each of the three
raw model predictions in `data/processed/week4_predictions.parquet` -- is
regressed per date on sector dummies (one level dropped, the catch-all
`sector == 0`) plus winsorised `beta_252` and `log_mcap`. The residual is then
cross-sectionally ranked and fed into the exact same `capped_neutral_weights`
/ `daily_book` machinery `week4_models.py` uses for the raw book, so the only
thing that changes between a raw and a neutralised book is the score.

Two things the exposures themselves force on this design:

  - `beta_252` ranges -10.9 to +7.1 (mean 1.20) on the aligned panel. Left
    unwinsorised those tails would dominate the per-date OLS. Winsorised at
    the 1st/99th percentile, cross-sectionally, matching the convention
    `factor_eval.cross_section_query` already uses for its own factor values.
  - Sector has 11 codes, one of them (`0`, the unclassifiable catch-all) so
    rare -- 378 rows out of 4.29M aligned rows across the whole 2014-2023
    span -- that most dates have zero members and some have exactly one.
    `np.linalg.lstsq` is used instead of a normal-equations inverse so a
    date like that still returns a residual instead of raising or emitting
    NaN.

`week4_models.book_frame` builds the raw (permno, date, tdi, rank, decile)
frame unchanged -- that machinery is reused, not reimplemented, and its raw
numbers must still reproduce the Week 4 headline. Only the score fed to
`capped_neutral_weights` differs for the neutralised side. `book` here is a
local variant of `week4_models.book` because it also needs `beta_252`,
`log_mcap` and per-sector pseudo-factors as extra `daily_book` exposures --
`week4_models`'s own version hard-codes `ALL_FACTORS`. Per-sector exposure
reuses `daily_book`'s existing `SUM(weight * (rank_f - 0.5))` mechanism with an
indicator "rank" (0 or 1) in place of a real percentile rank: since the book
is dollar-neutral, `SUM(weight * (indicator - 0.5)) = SUM(weight*indicator)`,
exactly the book's net weight in that sector.

Success is exactly the rule pre-declared in experiments.csv as W5-003, applied
here as: realised beta at least halved in magnitude AND net Sharpe at 10bp no
worse than the raw book. Neither side of this study clears a Newey-West
|t| of 1 anywhere (the Week 4 headline is HAC t=1.01), so a neutralised book
that "wins" is still inside the same noise band as the raw one, not a
discovery.

Formation window 2014-01-02..2023-11-30, P&L to 2023-12-29, identical to
Week 4. Nothing here reads a date past PNL_LAST.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.evaluation.factor_eval import newey_west_tstat, OVERLAP_LAG
from src.evaluation.week3_baseline import COMPOSITE
from src.evaluation.week4_models import NAMES, PNL_LAST, book_frame
from src.features.factors import ALL_FACTORS
from src.models.splits import walk_forward_splits
from src.models.walk_forward import COHORT_LAST, PREDICTIONS
from src.portfolio.backtest import (COSTS_BPS, TRADING_DAYS,
                                     capped_neutral_weights, daily_book, performance_daily)

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
EXPOSURES = ROOT / "data" / "processed" / "exposures"
OUT = ROOT / "reports" / "week5"

SECTORS = tuple(range(11))                    # SIC_DIVISION_CASE's 11 codes, 0 = catch-all
NEUTRAL_EXPOSURES = ("beta_252", "log_mcap")  # sector is reported as one aggregate below
EXPOSURE_FACTORS = tuple(ALL_FACTORS) + NEUTRAL_EXPOSURES + tuple(f"sector_{s}" for s in SECTORS)


def winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    """Cross-sectional 1st/99th percentile clip -- `factor_eval.py`'s own convention."""
    return s.clip(s.quantile(lower), s.quantile(upper))


def residualize(frame: pd.DataFrame) -> np.ndarray:
    """Per-date residual of `score` on sector dummies (`sector_0` dropped) plus
    `beta_252_w` and `log_mcap_w`. `frame` needs those four columns and `date`.

    `np.linalg.lstsq` rather than `(X'X)^-1 X'y`: a date whose design is rank
    deficient (an absent or single-member sector) still returns the min-norm
    least-squares residual instead of raising or producing NaN.
    """
    dummies = (pd.get_dummies(frame["sector"], prefix="sector")
               .reindex(columns=[f"sector_{s}" for s in SECTORS], fill_value=0.0)
               .drop(columns="sector_0").to_numpy(dtype=float))
    X = np.column_stack([np.ones(len(frame)), dummies,
                         frame["beta_252_w"].to_numpy(dtype=float),
                         frame["log_mcap_w"].to_numpy(dtype=float)])
    y = frame["score"].to_numpy(dtype=float)
    residual = np.empty(len(y))
    for _, pos in frame.groupby("date").indices.items():
        coef, *_ = np.linalg.lstsq(X[pos], y[pos], rcond=None)
        residual[pos] = y[pos] - X[pos] @ coef
    return residual


def neutralise(score_frame: pd.DataFrame, exposures: pd.DataFrame) -> pd.DataFrame:
    """Residualise `score_frame.score` against the three exposures, then
    cross-sectionally rank the residual into the same (rank, decile) shape
    `week4_models.book_frame` produces for the raw score."""
    merged = score_frame.merge(exposures, on=["permno", "date", "tdi"], validate="one_to_one")
    merged["residual"] = residualize(merged)
    merged["rank"] = merged.groupby("date")["residual"].rank(pct=True)
    pct = merged.groupby("date")["rank"].rank(pct=True)
    merged["decile"] = np.where(pct >= 0.9, 1.0, np.where(pct <= 0.1, -1.0, 0.0))
    return merged[["permno", "date", "tdi", "rank", "decile"]]


def raw_score_frame(raw_frame: pd.DataFrame, name: str, predictions: pd.DataFrame) -> pd.DataFrame:
    """The pre-rank score to residualise: the composite's own signed-rank
    average (`raw_frame["rank"]`, never itself re-ranked by `book_frame`), or
    a model's raw prediction column -- `book_frame` turns a model's prediction
    into a percentile rank before weighting, but residualisation happens
    upstream of that, on the prediction itself, per the pre-declared design."""
    if name == COMPOSITE:
        return raw_frame[["permno", "date", "tdi", "rank"]].rename(columns={"rank": "score"})
    return (predictions.loc[predictions.model == name, ["permno", "date", "tdi", "prediction"]]
            .rename(columns={"prediction": "score"}).reset_index(drop=True))


def merged_scan_query(factor_scan: str, exposures_scan: str, pnl_last: str) -> str:
    """factor_panel joined to exposures, plus `rank_beta_252`, `rank_log_mcap`
    (built exactly like `build_factor_panel.py` builds `rank_<factor>`: gated
    on `aligned`, ranked only among aligned rows) and one 0/1 pseudo-rank per
    sector, so `daily_book`'s existing `factors=` exposure mechanism can report
    on the three neutralisation exposures with no change to `backtest.py`."""
    sector_cols = ",\n            ".join(
        f"CASE WHEN aligned THEN (sector = {s})::DOUBLE END AS rank_sector_{s}" for s in SECTORS)
    return f"""
        WITH joined AS (
            SELECT fp.*, exp.sector, exp.beta_252, exp.log_mcap
            FROM {factor_scan} fp
            LEFT JOIN {exposures_scan} exp USING (permno, date, tdi)
            WHERE fp.date <= DATE '{pnl_last}'
        )
        SELECT *,
            CASE WHEN aligned THEN (RANK() OVER (PARTITION BY date ORDER BY beta_252) - 1.0)
                / NULLIF(COUNT(*) FILTER (aligned) OVER d - 1, 0) END AS rank_beta_252,
            CASE WHEN aligned THEN (RANK() OVER (PARTITION BY date ORDER BY log_mcap) - 1.0)
                / NULLIF(COUNT(*) FILTER (aligned) OVER d - 1, 0) END AS rank_log_mcap,
            {sector_cols}
        FROM joined
        WINDOW d AS (PARTITION BY date)
    """


def book(con, scan: str, frame: pd.DataFrame, weighting: str, first_date: str, last_date: str) -> pd.DataFrame:
    """`week4_models.book`, extended to also report the three neutralisation
    exposures alongside the six factors -- weights depend only on `frame`'s
    `rank`/`decile` column, so raw and neutralised P&L is unaffected."""
    cohort = frame[["permno", "tdi", "date"]].copy()
    cohort["w"] = capped_neutral_weights(frame, weighting)
    con.register("cohort", cohort[["permno", "tdi", "w"]])
    daily = daily_book(con, scan, first_date, last_date, factors=EXPOSURE_FACTORS)
    con.unregister("cohort")
    return daily


def daily_rank_ic(con, scan: str, frame: pd.DataFrame) -> pd.Series:
    """Daily Spearman rank IC of `frame.rank` against the realised 20-day
    forward return, matching the correlation-of-percentile-ranks construction
    `week4_models.prediction_quality` and `factor_eval.cross_section_query`
    both use."""
    con.register("scored", frame[["permno", "tdi", "rank"]])
    ic = con.sql(f"""
        WITH y AS (
            SELECT permno, tdi, date,
                (RANK() OVER (PARTITION BY date ORDER BY forward_return_20d) - 1.0)
                    / NULLIF(COUNT(*) OVER (PARTITION BY date) - 1, 0) AS y_rank
            FROM {scan} WHERE forward_return_20d IS NOT NULL
        )
        SELECT y.date, corr(scored.rank, y.y_rank) AS ic
        FROM scored JOIN y USING (permno, tdi)
        GROUP BY y.date ORDER BY y.date
    """).df()
    con.unregister("scored")
    return ic.set_index("date")["ic"]


def summarize(daily: pd.DataFrame, ic: pd.Series) -> dict:
    """Book statistics: the same block `week4_models.summarize` reports, plus
    mean rank IC/HAC-t and the three neutralisation exposures."""
    summary = {
        "days": len(daily),
        "first_date": str(daily.date.min().date()), "last_date": str(daily.date.max().date()),
        "mean_rank_ic": ic.mean(), "rank_ic_hac_t": newey_west_tstat(ic.dropna(), OVERLAP_LAG),
        "mean_gross_exposure": daily.gross_exposure.mean(),
        "annual_turnover": daily.turnover.mean() * TRADING_DAYS,
        "breakeven_bp": 1e4 * daily.gross_return.mean() / daily.traded.mean(),
    }
    for column in ["gross_return"] + [f"net_return_{b}bp" for b in COSTS_BPS]:
        for key, value in performance_daily(daily[column], daily.market_return).items():
            summary[f"{column}_{key}"] = value
    summary["gross_return_hac_t"] = newey_west_tstat(daily.gross_return, OVERLAP_LAG)
    for factor in list(ALL_FACTORS) + list(NEUTRAL_EXPOSURES):
        summary[f"exposure_{factor}"] = daily[f"exposure_{factor}"].mean()
    # Total gross sector tilt: mean-over-days of the sum of |net weight| across
    # sectors. Sum-then-mean equals mean-then-sum (both are over disjoint
    # indices), so this is exact, not an approximation.
    summary["exposure_sector"] = sum(daily[f"exposure_sector_{s}"].abs().mean() for s in SECTORS)
    return summary


def verdict(raw: dict, neutral: dict) -> tuple:
    """W5-003's pre-declared rule, applied as written: beta materially closer
    to zero (operationalised here as at least halved in magnitude -- stated
    explicitly since "materially" is not itself a number) AND net Sharpe at
    10bp no worse than the raw book. A beta improvement bought with a worse
    net Sharpe is a FAILURE, not a partial win."""
    raw_beta, neutral_beta = raw["gross_return_market_beta"], neutral["gross_return_market_beta"]
    beta_closer = abs(neutral_beta) <= 0.5 * abs(raw_beta)
    net_ok = neutral["net_return_10bp_sharpe"] >= raw["net_return_10bp_sharpe"]
    return (beta_closer and net_ok), beta_closer, net_ok


def figure(daily: dict, summary: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    pair = {"raw": COMPOSITE, "neutral": f"{COMPOSITE}__neutral"}

    for label, key in pair.items():
        d = daily[key].set_index("date")
        (1 + d.gross_return).cumprod().plot(ax=ax[0, 0], lw=1, label=label)
    ax[0, 0].set_title(f"{COMPOSITE}: cumulative gross return, raw vs neutralised")
    ax[0, 0].legend(fontsize=8)

    for label, key in pair.items():
        d = daily[key].set_index("date")
        beta = (d.gross_return.rolling(252).cov(d.market_return)
                / d.market_return.rolling(252).var())
        beta.plot(ax=ax[0, 1], lw=1, label=label)
    ax[0, 1].axhline(0, color="k", lw=0.8)
    ax[0, 1].set_title("Rolling 252-day market beta, raw vs neutralised")
    ax[0, 1].legend(fontsize=8)

    exposures = list(ALL_FACTORS) + list(NEUTRAL_EXPOSURES)
    x = np.arange(len(exposures))
    width = 0.35
    for i, (label, key) in enumerate(pair.items()):
        values = summary.loc[[f"exposure_{e}" for e in exposures], key].values
        ax[1, 0].bar(x + (i - 0.5) * width, values, width, label=label)
    ax[1, 0].axhline(0, color="k", lw=0.8)
    ax[1, 0].set_xticks(x, exposures, rotation=45, ha="right", fontsize=7)
    ax[1, 0].set_title(f"{COMPOSITE}: mean factor/exposure loadings, raw vs neutralised")
    ax[1, 0].legend(fontsize=8)

    costs = [0] + COSTS_BPS
    for label, key in pair.items():
        sharpes = [summary.loc["gross_return_sharpe", key]] + [
            summary.loc[f"net_return_{b}bp_sharpe", key] for b in COSTS_BPS]
        ax[1, 1].plot(costs, sharpes, marker="o", ms=3, label=label)
    ax[1, 1].axhline(0, color="k", lw=0.8)
    ax[1, 1].set_xlabel("cost, bp of traded notional")
    ax[1, 1].set_title(f"{COMPOSITE}: net Sharpe versus cost, raw vs neutralised")
    ax[1, 1].legend(fontsize=8)

    fig.suptitle("Week 5: sector/beta/size neutralisation, W5-003, 2014-2023 "
                 "(everything here sits inside the noise band, HAC |t| ~1.0)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    if not EXPOSURES.exists():
        sys.exit("Exposures not found. Run src/features/exposures.py first.")
    if not PREDICTIONS.exists():
        sys.exit("Week 4 predictions not found. Run src/models/walk_forward.py first.")
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    exp_scan = f"parquet_scan('{(EXPOSURES / '**' / '*.parquet').as_posix()}')"

    predictions = pd.read_parquet(PREDICTIONS)
    assert predictions.date.max() <= pd.Timestamp(COHORT_LAST), "prediction past the sealed period"
    assert predictions.is_validation.all(), "expected validation-only predictions"

    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)
    first_date = str(splits.validation_start.min())
    assert predictions.date.min() == pd.Timestamp(first_date), \
        "predictions still carry a warm-up block before the first validation date"

    print("Materialising the merged factor/exposure panel...", flush=True)
    con.execute(f"CREATE TABLE merged_panel AS {merged_scan_query(scan, exp_scan, PNL_LAST)}")
    print(f"merged_panel: {con.sql('SELECT COUNT(*) FROM merged_panel').fetchone()[0]:,} rows\n", flush=True)

    exposures = con.sql(f"""
        SELECT exp.permno, exp.date, exp.tdi, exp.sector, exp.beta_252, exp.log_mcap
        FROM {exp_scan} exp JOIN {scan} fp USING (permno, date, tdi)
        WHERE fp.aligned AND fp.date >= DATE '{first_date}' AND fp.date <= DATE '{COHORT_LAST}'
    """).df()
    exposures["beta_252_w"] = exposures.groupby("date")["beta_252"].transform(winsorize)
    exposures["log_mcap_w"] = exposures.groupby("date")["log_mcap"].transform(winsorize)

    daily, summaries = {}, []
    for name in NAMES:
        raw_frame = book_frame(con, scan, name, predictions, first_date)
        assert raw_frame.date.max() <= pd.Timestamp(COHORT_LAST), f"{name}: cohort formed past 2023-11-30"
        neutral_frame = neutralise(raw_score_frame(raw_frame, name, predictions), exposures)
        assert not neutral_frame[["rank", "decile"]].isna().any().any(), f"{name}: NaN in neutralised score"

        frames = {name: raw_frame, f"{name}__neutral": neutral_frame}
        ics = {label: daily_rank_ic(con, scan, frame) for label, frame in frames.items()}

        for label, frame in frames.items():
            for weighting in ("rank", "decile"):
                book_label = label if weighting == "rank" else f"{label}__decile"
                d = book(con, "merged_panel", frame, weighting, first_date, PNL_LAST)
                assert d.date.is_monotonic_increasing and not d.date.duplicated().any()
                assert d.date.max() <= pd.Timestamp(PNL_LAST)
                daily[book_label] = d
                s = summarize(d, ics[label])
                summaries.append(pd.Series(s, name=book_label))
                if "__neutral" in book_label:
                    d.to_csv(OUT / f"daily_{book_label}.csv", index=False)
                print(f"{book_label:28s} days {len(d):5d}  gross SR {s['gross_return_sharpe']:6.3f}",
                      flush=True)

    reference_dates = next(iter(daily.values())).date.reset_index(drop=True)
    for label, d in daily.items():
        assert (d.date.reset_index(drop=True) == reference_dates).all(), \
            f"{label}: date index differs from the other books"

    summary = pd.concat(summaries, axis=1)
    summary.to_csv(OUT / "neutralisation.csv")

    rows = []
    for name in NAMES:
        for weighting in ("rank", "decile"):
            raw_label = name if weighting == "rank" else f"{name}__decile"
            neutral_label = f"{name}__neutral" if weighting == "rank" else f"{name}__neutral__decile"
            raw_s, neutral_s = summary[raw_label], summary[neutral_label]
            passed, beta_closer, net_ok = verdict(raw_s, neutral_s)
            rows.append({
                "name": name, "weighting": weighting,
                "raw_beta": raw_s["gross_return_market_beta"],
                "neutral_beta": neutral_s["gross_return_market_beta"],
                "raw_net_sharpe_10bp": raw_s["net_return_10bp_sharpe"],
                "neutral_net_sharpe_10bp": neutral_s["net_return_10bp_sharpe"],
                "raw_gross_sharpe": raw_s["gross_return_sharpe"],
                "neutral_gross_sharpe": neutral_s["gross_return_sharpe"],
                "raw_exposure_sector": raw_s["exposure_sector"],
                "neutral_exposure_sector": neutral_s["exposure_sector"],
                "beta_materially_closer_to_zero": beta_closer,
                "net_sharpe_no_worse": net_ok,
                "w5_003_verdict": "PASS" if passed else "FAIL",
            })
    verdicts = pd.DataFrame(rows)
    verdicts.to_csv(OUT / "w5_003_verdict.csv", index=False)
    print("\nW5-003 verdict (beta materially closer to zero = at least halved in "
          "magnitude, AND net Sharpe at 10bp no worse than raw):\n",
          verdicts.round(4).to_string(index=False))

    figure(daily, summary, OUT / "diagnostics.png")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
