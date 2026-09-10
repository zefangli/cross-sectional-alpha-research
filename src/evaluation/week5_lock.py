"""W5-006: lock a single specification, built programmatically from every
candidate book Weeks 3-5 produced -- not hand-picked.

The candidate grid was incomplete until `week5_ablation_neutral.py` ran: it
crossed {weighting} x {neutralisation} for the full six-factor set and
ablated the raw composite, but never neutralised an ablated composite. Every
raw ablation fails the beta constraint (`ablation.csv`), so an alternative
factor set never had a genuine chance to win under the pre-declared rule.
With that gap closed, this module assembles all four sources -- Week 4 raw
books, Week 5 neutralised books, the raw ablations, and the new neutralised
ablations -- into one table and applies the W5-006 rule exactly as declared
in `experiments.csv`: maximise net Sharpe at 10bp subject to |realised market
beta| <= 0.10. The rule itself is not touched; only the grid it is applied to
grows. If the winner changes, that is the point of closing the gap, not a
reason to keep the old one.

Book names follow the `<base>[__neutral][__decile]` convention every Week 4/5
module already uses, so `classify` recovers weighting/neutralisation/factor
set from the name alone rather than carrying that metadata separately through
four different source files.
"""
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src.evaluation.week5_robustness import PNL_LAST, WEIGHTINGS, add_signal, book, composite_frame, summarize
from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.models.splits import walk_forward_splits
from src.models.walk_forward import COHORT_LAST
from src.portfolio.backtest import CAP, HOLD_DAYS

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "week5"
BETA_LIMIT = 0.10


def classify(name: str) -> dict:
    """Weighting/neutralisation/factor-set implied by a book's own name."""
    weighting = "decile" if name.endswith("__decile") else "rank"
    base = name[: -len("__decile")] if weighting == "decile" else name
    neutralised = base.endswith("__neutral")
    if neutralised:
        base = base[: -len("__neutral")]
    factor_set = "all_six" if base == "composite" else base
    return {"factor_set": factor_set, "neutralised": neutralised, "weighting": weighting}


def week4_raw_rows() -> pd.DataFrame:
    """The 8 raw Week 4 books -- three fitted models and the composite, both weightings."""
    mc = pd.read_csv(OUT.parent / "week4" / "model_comparison.csv")
    return pd.DataFrame([{
        "book": r.book, **classify(r.book),
        "gross_sharpe": r.gross_sharpe, "gross_hac_t": r.gross_hac_tstat,
        "net_sharpe_10bp": r.net_sharpe_10bp, "breakeven_bp": r.breakeven_bp,
        "annual_turnover": r.annual_turnover, "realised_beta": r.beta,
        "max_drawdown": r.max_drawdown,
    } for r in mc.itertuples()])


def week5_neutral_rows() -> pd.DataFrame:
    """The 8 neutralised Week 4 books, read from `neutralisation.csv`'s wide summary."""
    wide = pd.read_csv(OUT / "neutralisation.csv", index_col=0)
    rows = []
    for name in wide.columns:
        if "__neutral" not in name:
            continue
        s = wide[name]
        rows.append({
            "book": name, **classify(name),
            "gross_sharpe": float(s["gross_return_sharpe"]), "gross_hac_t": float(s["gross_return_hac_t"]),
            "net_sharpe_10bp": float(s["net_return_10bp_sharpe"]), "breakeven_bp": float(s["breakeven_bp"]),
            "annual_turnover": float(s["annual_turnover"]),
            "realised_beta": float(s["gross_return_market_beta"]),
            "max_drawdown": float(s["gross_return_max_drawdown"]),
        })
    return pd.DataFrame(rows)


def raw_ablation_rows(con, scan: str, first_date: str) -> pd.DataFrame:
    """The 12 raw leave-one-out ablations. Recomputed here (via the same
    `composite_frame`/`add_signal`/`book`/`summarize` `ablation.csv` was built
    from) only because `ablation.csv` never kept `max_drawdown`; the 'full'
    rows are dropped since they duplicate the Week 4 composite already in
    `week4_raw_rows`."""
    raw_frame = composite_frame(con, scan, first_date, COHORT_LAST)
    rows = []
    for dropped in ALL_FACTORS:
        kept = [f for f in ALL_FACTORS if f != dropped]
        frame = add_signal(raw_frame, kept)
        base = f"drop_{dropped}"
        for weighting in WEIGHTINGS:
            daily = book(con, scan, frame, weighting, first_date, PNL_LAST)
            s = summarize(daily)
            name = base if weighting == "rank" else f"{base}__decile"
            rows.append({
                "book": name, "factor_set": base, "neutralised": False, "weighting": weighting,
                "gross_sharpe": s["gross_return_sharpe"], "gross_hac_t": s["hac_t"],
                "net_sharpe_10bp": s["net_return_10bp_sharpe"], "breakeven_bp": s["breakeven_bp"],
                "annual_turnover": s["annual_turnover"], "realised_beta": s["gross_return_market_beta"],
                "max_drawdown": s["gross_return_max_drawdown"],
            })
    return pd.DataFrame(rows)


def neutral_ablation_rows() -> pd.DataFrame:
    """The 12 books this whole lock exists to add, from `week5_ablation_neutral.py`'s output."""
    t = pd.read_csv(OUT / "ablation_neutral.csv")
    return pd.DataFrame([{
        "book": r.book, "factor_set": f"drop_{r.dropped}", "neutralised": True,
        "weighting": r.weighting, "gross_sharpe": r.gross_sharpe, "gross_hac_t": r.hac_t,
        "net_sharpe_10bp": r.net_sharpe_10bp, "breakeven_bp": r.breakeven_bp,
        "annual_turnover": r.annual_turnover, "realised_beta": r.beta,
        "max_drawdown": r.max_drawdown,
    } for r in t.itertuples()])


def candidate_table(con, scan: str, first_date: str) -> pd.DataFrame:
    """Every candidate book from Weeks 3-5, one row each."""
    table = pd.concat([week4_raw_rows(), week5_neutral_rows(),
                        raw_ablation_rows(con, scan, first_date), neutral_ablation_rows()],
                       ignore_index=True)
    assert not table.book.duplicated().any(), "duplicate book label across candidate sources"
    return table


def select(table: pd.DataFrame, beta_limit: float = BETA_LIMIT) -> pd.DataFrame:
    """W5-006's rule, applied exactly as declared: among rows within the beta
    constraint, rank by net Sharpe at 10bp descending."""
    passing = table[table.realised_beta.abs() <= beta_limit]
    return passing.sort_values("net_sharpe_10bp", ascending=False).reset_index(drop=True)


def parameterisation(row: pd.Series) -> dict:
    """The winning book's full construction: factor names and signs (or `None`
    for a fitted model, which has no hand-assigned factor signs), neutralisation
    controls, weighting, hold length and cap."""
    factor_set = row.factor_set
    if factor_set == "all_six":
        factors = [{"name": f, "sign": FACTOR_SIGN[f]} for f in ALL_FACTORS]
    elif factor_set.startswith("drop_"):
        dropped = factor_set[len("drop_"):]
        factors = [{"name": f, "sign": FACTOR_SIGN[f]} for f in ALL_FACTORS if f != dropped]
    else:
        factors = None  # a fitted model's prediction, not a hand-built composite

    spec = {"factor_set": factor_set, "factors": factors, "weighting": row.weighting,
            "hold_days": HOLD_DAYS, "cap": CAP, "neutralised": bool(row.neutralised)}
    if row.neutralised:
        spec["neutralisation"] = {
            "regressors": ["sector dummies (10 of 11 SIC divisions; sector_0 dropped)",
                           "beta_252 (cross-sectionally winsorised)",
                           "log_mcap (cross-sectionally winsorised)"],
            "winsorise_quantiles": [0.01, 0.99],
            "solver": "np.linalg.lstsq (rank-tolerant, per date)",
        }
    return spec


def main() -> None:
    import duckdb

    ablation_neutral_csv = OUT / "ablation_neutral.csv"
    if not ablation_neutral_csv.exists():
        sys.exit("Run src/evaluation/week5_ablation_neutral.py first.")

    con = duckdb.connect()
    panel = ROOT / "data" / "processed" / "factor_panel"
    scan = f"parquet_scan('{(panel / '**' / '*.parquet').as_posix()}')"
    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)
    first_date = str(splits.validation_start.min())

    table = candidate_table(con, scan, first_date)
    table.to_csv(OUT / "candidates.csv", index=False)

    passing = select(table)
    commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, text=True).strip()
    common = {"rule": "max net Sharpe at 10bp subject to |realised market beta| <= 0.10",
              "candidates": int(len(table)), "passing_beta_constraint": int(len(passing)),
              "declared_in": "W5-006", "locked_on": str(pd.Timestamp.today().date()),
              "git_commit": commit}

    if passing.empty:
        lock = {"locked_book": None, **common,
                "note": "no candidate satisfies the beta constraint; reported as unmet, not relaxed"}
    else:
        winner = passing.iloc[0]
        runner_up = passing.iloc[1] if len(passing) > 1 else None
        lock = {
            "locked_book": winner.book, **common, **parameterisation(winner),
            "realised_beta": float(winner.realised_beta),
            "net_sharpe_10bp": float(winner.net_sharpe_10bp),
            "gross_sharpe": float(winner.gross_sharpe), "gross_hac_t": float(winner.gross_hac_t),
            "max_drawdown": float(winner.max_drawdown),
            "runner_up": None if runner_up is None else {
                "book": runner_up.book, "net_sharpe_10bp": float(runner_up.net_sharpe_10bp),
                "margin": float(winner.net_sharpe_10bp - runner_up.net_sharpe_10bp),
            },
        }

    (OUT / "locked_specification.json").write_text(json.dumps(lock, indent=2))

    display = table.assign(beta_ok=table.realised_beta.abs() <= BETA_LIMIT) \
        .sort_values("net_sharpe_10bp", ascending=False)
    print(f"Candidates: {len(table)}, passing beta constraint: {len(passing)}\n")
    print(display.round(4).to_string(index=False))
    if not passing.empty:
        print(f"\nLocked: {lock['locked_book']}  net@10bp {lock['net_sharpe_10bp']:.4f}  "
              f"beta {lock['realised_beta']:.4f}  gross SR {lock['gross_sharpe']:.4f}")
        if lock["runner_up"]:
            print(f"Runner-up: {lock['runner_up']['book']}  "
                  f"net@10bp {lock['runner_up']['net_sharpe_10bp']:.4f}  "
                  f"margin {lock['runner_up']['margin']:.4f}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
