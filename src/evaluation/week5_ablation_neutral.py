"""W5-006 candidate-grid gap: neutralised leave-one-out ablations.

W5-004 ablated the raw six-factor composite; W5-003 neutralised the full
six-factor composite and each fitted model. Neither study ever neutralised an
ablated composite, so the 12 books that would tell whether an alternative
factor set can pass the W5-006 beta constraint (every raw ablation fails it,
per `ablation.csv`) were never built. This module builds exactly those 12:
for each of the six factors dropped in turn, the equal-weighted signed-rank
composite of the remaining five is residualised, ranked and run through the
unchanged continuous backtest under both weightings.

Nothing here reimplements neutralisation or the backtest. The five-factor
composite reuses `week5_robustness.add_signal`; the residualisation, ranking,
exposure panel and book construction reuse `week5_neutral.neutralise`,
`formation_exposures`, `merged_scan_query`, `book`, `daily_rank_ic` and
`summarize` verbatim -- the only new code is wiring an arbitrary five-factor
score into that existing pipeline instead of the full six.

Same conventions as every other Week 5 module: formation 2014-01-02 ..
2023-11-30, P&L to 2023-12-29, dollar-neutral, 1% cap, 20-day staggered
cohorts, Newey-West t at 20 lags. Nothing here reads a date past PNL_LAST.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src.evaluation.week4_models import PNL_LAST
from src.evaluation.week5_neutral import (EXPOSURES, PANEL, book, daily_rank_ic,
                                           formation_exposures, merged_scan_query,
                                           neutralise, summarize)
from src.evaluation.week5_robustness import add_signal, composite_frame
from src.features.factors import ALL_FACTORS
from src.models.splits import walk_forward_splits
from src.models.walk_forward import COHORT_LAST

OUT = Path(__file__).resolve().parents[2] / "reports" / "week5"


def dropped_composite(raw_frame: pd.DataFrame, dropped: str) -> pd.DataFrame:
    """Equal-weighted signed-rank composite of the five factors that remain
    after dropping `dropped` -- the leave-one-out row W5-003/W5-004 never
    neutralised."""
    kept = [f for f in ALL_FACTORS if f != dropped]
    return add_signal(raw_frame, kept)


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """`frame.rank` (the pre-neutralisation composite) as the `neutralise`-ready score."""
    return frame[["permno", "date", "tdi", "rank"]].rename(columns={"rank": "score"})


def summary_row(dropped: str, weighting: str, s: dict) -> dict:
    """One row of `ablation_neutral.csv`, the neutral-side counterpart of `ablation.csv`
    plus the rank-IC and drawdown fields `neutralisation.csv` also reports."""
    return {
        "dropped": dropped, "weighting": weighting,
        "gross_sharpe": s["gross_return_sharpe"], "hac_t": s["gross_return_hac_t"],
        "net_sharpe_1bp": s["net_return_1bp_sharpe"],
        "net_sharpe_5bp": s["net_return_5bp_sharpe"],
        "net_sharpe_10bp": s["net_return_10bp_sharpe"],
        "net_sharpe_20bp": s["net_return_20bp_sharpe"],
        "breakeven_bp": s["breakeven_bp"], "annual_turnover": s["annual_turnover"],
        "beta": s["gross_return_market_beta"], "max_drawdown": s["gross_return_max_drawdown"],
        "mean_rank_ic": s["mean_rank_ic"], "rank_ic_hac_t": s["rank_ic_hac_t"],
    }


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    if not EXPOSURES.exists():
        sys.exit("Exposures not found. Run src/features/exposures.py first.")
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    exp_scan = f"parquet_scan('{(EXPOSURES / '**' / '*.parquet').as_posix()}')"

    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)
    first_date = str(splits.validation_start.min())

    print("Materialising the merged factor/exposure panel...", flush=True)
    con.execute(f"CREATE TABLE merged_panel AS {merged_scan_query(scan, exp_scan, PNL_LAST)}")

    exposures = formation_exposures(con, exp_scan, scan, first_date)
    raw_frame = composite_frame(con, scan, first_date, COHORT_LAST)
    assert raw_frame.date.max() <= pd.Timestamp(COHORT_LAST), "cohort formed past 2023-11-30"

    daily, rows = {}, []
    for dropped in ALL_FACTORS:
        five = dropped_composite(raw_frame, dropped)
        neutral_frame = neutralise(score_frame(five), exposures)
        assert not neutral_frame[["rank", "decile"]].isna().any().any(), \
            f"drop_{dropped}: NaN in neutralised score"
        ic = daily_rank_ic(con, scan, neutral_frame)

        base = f"drop_{dropped}__neutral"
        for weighting in ("rank", "decile"):
            book_label = base if weighting == "rank" else f"{base}__decile"
            d = book(con, "merged_panel", neutral_frame, weighting, first_date, PNL_LAST)
            assert d.date.is_monotonic_increasing and not d.date.duplicated().any()
            assert d.date.max() <= pd.Timestamp(PNL_LAST)
            daily[book_label] = d
            s = summarize(d, ic)
            row = summary_row(dropped, weighting, s)
            row["book"] = book_label
            rows.append(row)
            d.to_csv(OUT / f"daily_{book_label}.csv", index=False)
            print(f"{book_label:30s} days {len(d):5d}  gross SR {s['gross_return_sharpe']:6.3f}  "
                  f"net@10bp {s['net_return_10bp_sharpe']:6.3f}  beta {s['gross_return_market_beta']:6.3f}",
                  flush=True)

    reference_dates = next(iter(daily.values())).date.reset_index(drop=True)
    for label, d in daily.items():
        assert (d.date.reset_index(drop=True) == reference_dates).all(), \
            f"{label}: date index differs from the other books"

    table = pd.DataFrame(rows)[["book", "dropped", "weighting", "gross_sharpe", "hac_t",
                                 "net_sharpe_1bp", "net_sharpe_5bp", "net_sharpe_10bp",
                                 "net_sharpe_20bp", "breakeven_bp", "annual_turnover", "beta",
                                 "max_drawdown", "mean_rank_ic", "rank_ic_hac_t"]]
    table.to_csv(OUT / "ablation_neutral.csv", index=False)
    print("\nNeutralised ablation (the 12 books W5-006's grid was missing):\n",
          table.round(4).to_string(index=False))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
