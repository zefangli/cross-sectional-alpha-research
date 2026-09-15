"""Post-fix research recomputation — not a sealed test.

Writes only under ``reports/post_fix/``. Leaves ``reports/`` (including the
original sealed ``reports/week6`` artifacts) untouched as the pre-fix record.

2024–2025 is recomputed as a labelled **post-fix audit** of the same locked
specification; it does not call the sealed-run marker and does not overwrite
``final_*.csv`` / ``sealed_run_started.json``.

Steps (``--from-step N`` resumes):
  1. Re-clean the raw export (identity-only scope, so held names keep marking).
  2. Rebuild the research panel (t-1 eligibility).
  3. Rebuild the factor panel (aligned-rank fix).
  4. Rebuild risk exposures (they read the cleaned panel).
  5. Rebuild Week 4 walk-forward predictions (ranks are model features).
  6. Re-run Week 2 single-factor evaluation into ``reports/post_fix/week2/``.
  7. Re-run Weeks 3–5 evaluation into ``reports/post_fix/``.
  8. Run the 2024–2025 locked-book audit into ``reports/post_fix/week6_audit/``
     and write ``reports/post_fix/week5/replay_targets.json`` for
     ``week6_final.py replay``.

Usage (conda base)::

    python -m src.evaluation.run_post_fix_audit
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REPORTS_PRE = ROOT / "reports"  # pre-fix; never written by this script
POST = ROOT / "reports" / "post_fix"
PANEL = ROOT / "data" / "processed" / "factor_panel"
PREDICTIONS = ROOT / "data" / "processed" / "week4_predictions.parquet"
PREDICTIONS_PRE = ROOT / "data" / "processed" / "week4_predictions_pre_fix.parquet"
SPEC_PATH = ROOT / "reports" / "week5" / "locked_specification.json"


DUCKDB_MEMORY_LIMIT = "5GB"


def cap_duckdb_memory() -> None:
    """Every stage opens its own DuckDB connection; cap them all here.

    DuckDB defaults to 80% of RAM, and Week 5 materialises a 20M-row merged
    panel alongside pandas frames, which on a 16 GB machine got the process
    killed by the OS mid-run (no traceback, partial `reports/post_fix/week5/`).
    A modest limit plus a spill directory makes it spill to disk instead. Set
    in this runner only, so a single-stage run keeps DuckDB's own defaults.
    """
    import duckdb
    spill = ROOT / "data" / "interim" / "duckdb_spill"
    spill.mkdir(parents=True, exist_ok=True)
    original = duckdb.connect

    def connect(*args, **kwargs):
        con = original(*args, **kwargs)
        con.execute(f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'")
        con.execute(f"SET temp_directory='{spill.as_posix()}'")
        con.execute("SET preserve_insertion_order=false")
        return con

    duckdb.connect = connect


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_readme() -> None:
    POST.mkdir(parents=True, exist_ok=True)
    (POST / "README.md").write_text(
        f"""# Post-fix research recomputation

Generated: {_stamp()}

These outputs were recomputed **after** the source corrections to factor ranks,
backtest turnover / holdings / terminal costs, missing-return handling, Spearman
IC, drift-aware trading, formation-versus-evaluation separation, t-1 eligibility
and the cleaner's marking scope (2026-09-14 review), then delisting event rows,
observed-window marking in Week 2 and the gap-trade diagnostic (2026-09-15
follow-up). They are a **correction audit**, not a second sealed test.

| Location | Role |
|----------|------|
| `reports/` (sibling of this folder) | **Pre-fix** research record, including the original sealed 2024–2025 artifacts under `reports/week6/` |
| `reports/post_fix/` (this tree) | Corrected recomputation |
| `reports/post_fix/week6_audit/` | 2024–2025 locked-book **audit** (same specification; separate label; sealed files untouched) |

**Missing-return policy:** held names with NULL daily `ret` (delistings / gaps in
this CRSP export, which has no delisting-return field) accrue **0** that day and
are counted in `positions_without_return`. They are not dropped from the P&L sum
via SQL NULL-skipping, and they do not abort the run.

Do not treat `week6_audit` as replacing the sealed one-shot result. Compare it
to `reports/week6/` when auditing how the bug fixes change the held-out numbers.
""",
        encoding="utf-8",
    )


def _rebuild(module, out_dir: Path) -> None:
    """Rebuild one partitioned data product from scratch, never merging stale
    partitions into a fresh write."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    module.main()


def reclean() -> None:
    print("\n=== 1/8 Re-clean the raw export ===", flush=True)
    from src.data import clean_crsp
    _rebuild(clean_crsp, clean_crsp.OUT)


def rebuild_research_panel() -> None:
    print("\n=== 2/8 Rebuild research panel ===", flush=True)
    from src.data import build_research_panel
    _rebuild(build_research_panel, build_research_panel.OUT)


def rebuild_factor_panel() -> None:
    print("\n=== 3/8 Rebuild factor panel ===", flush=True)
    from src.features import build_factor_panel
    _rebuild(build_factor_panel, PANEL)


def rebuild_exposures() -> None:
    print("\n=== 4/8 Rebuild exposures ===", flush=True)
    from src.features import exposures
    _rebuild(exposures, exposures.OUT)


def rebuild_predictions() -> None:
    print("\n=== 5/8 Rebuild Week 4 walk-forward predictions ===", flush=True)
    if PREDICTIONS.exists() and not PREDICTIONS_PRE.exists():
        shutil.copy2(PREDICTIONS, PREDICTIONS_PRE)
        print(f"Preserved pre-fix predictions -> {PREDICTIONS_PRE}", flush=True)
    from src.models import walk_forward
    walk_forward.OUT = POST / "week4"
    walk_forward.OUT.mkdir(parents=True, exist_ok=True)
    walk_forward.main()


def run_week2() -> None:
    print("\n=== 6/8 Week 2 single-factor evaluation -> reports/post_fix/week2 ===", flush=True)
    import src.evaluation.factor_eval as week2
    week2.REPORTS = POST / "week2"
    week2.REPORTS.mkdir(parents=True, exist_ok=True)
    from src.features.factors import ALL_FACTORS
    week2.main(names=ALL_FACTORS)   # never let this runner's own flags reach it


def run_week_modules() -> None:
    print("\n=== 7/8 Weeks 3-5 -> reports/post_fix/ ===", flush=True)
    import src.evaluation.week3_baseline as week3
    import src.evaluation.week4_models as week4
    import src.evaluation.week5_neutral as week5n
    import src.evaluation.week5_robustness as week5r
    import src.evaluation.week5_ablation_neutral as week5a

    for mod, sub in (
        (week3, "week3"),
        (week4, "week4"),
        (week5n, "week5"),
        (week5r, "week5"),
        (week5a, "week5"),
    ):
        mod.OUT = POST / sub
        print(f"\n--- {mod.__name__} -> {mod.OUT} ---", flush=True)
        mod.main()


def write_replay_targets(spec: dict) -> None:
    """The locked book's corrected 2014-2023 numbers, so `week6_final.py replay
    reports/post_fix/week5/replay_targets.json` reproduces the corrected
    recomputation while the lock itself stays untouched."""
    import pandas as pd
    rows = pd.read_csv(POST / "week5" / "ablation_neutral.csv")
    row = rows[rows.book == spec["locked_book"]]
    assert len(row) == 1, f"locked book {spec['locked_book']} not found once in ablation_neutral.csv"
    row = row.iloc[0]
    targets = {"source": "reports/post_fix/week5/ablation_neutral.csv", "book": spec["locked_book"],
               "realised_beta": float(row.beta), "net_sharpe_10bp": float(row.net_sharpe_10bp),
               "gross_sharpe": float(row.gross_sharpe), "gross_hac_t": float(row.hac_t),
               "max_drawdown": float(row.max_drawdown)}
    (POST / "week5" / "replay_targets.json").write_text(json.dumps(targets, indent=2), encoding="utf-8")


def audit_2024_2025() -> dict:
    """Locked-book P&L on 2024–2025 as a labelled post-fix audit."""
    print("\n=== 8/8 Post-fix audit of 2024–2025 (not a sealed run) ===", flush=True)
    import duckdb
    import pandas as pd
    from src.evaluation import week6_final as w6

    out = POST / "week6_audit"
    out.mkdir(parents=True, exist_ok=True)

    # Refuse to touch sealed artifacts
    for name in w6.FINAL_ARTIFACT_NAMES + (w6.MARKER_NAME,):
        sealed = REPORTS_PRE / "week6" / name
        assert sealed.exists(), f"expected original sealed artifact missing: {sealed}"

    spec = w6.load_spec()
    write_replay_targets(spec)
    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    exp_scan = f"parquet_scan('{(w6.EXPOSURES / '**' / '*.parquet').as_posix()}')"

    first_date = w6.sealed_formation_start(con, scan)
    cohort_last = w6.cohort_cutoff(con, scan, w6.SEALED_PNL_LAST, spec["hold_days"])
    daily, summary, coverage = w6.run_locked_book(
        con, scan, exp_scan, spec, first_date, cohort_last, w6.SEALED_PNL_LAST)

    protocol = w6.frozen_protocol(
        spec, first_date, cohort_last, w6.SEALED_PNL_LAST, sealed=False,
        metric_coverage=coverage)
    protocol["audit"] = True
    protocol["label"] = "post_fix_audit_2024_2025"
    protocol["note"] = (
        "Correction audit after source bug fixes. Not a sealed one-shot test. "
        "Original sealed artifacts remain under reports/week6/."
    )
    protocol["generated_at"] = _stamp()

    daily.to_csv(out / "audit_daily.csv", index=False)
    pd.Series(summary).to_csv(out / "audit_result.csv")
    (out / "audit_protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")

    # Side-by-side headline vs sealed (if present)
    sealed_result = REPORTS_PRE / "week6" / "final_result.csv"
    comparison = {
        "label": "post_fix_audit_vs_sealed",
        "generated_at": _stamp(),
        "audit": {
            "gross_return_sharpe": float(summary["gross_return_sharpe"]),
            "net_return_10bp_sharpe": float(summary["net_return_10bp_sharpe"]),
            "gross_return_market_beta": float(summary["gross_return_market_beta"]),
            "mean_rank_ic": float(summary["mean_rank_ic"]),
            "days": int(summary["days"]),
        },
    }
    if sealed_result.exists():
        sealed = pd.read_csv(sealed_result, index_col=0).squeeze("columns")
        comparison["sealed_pre_fix"] = {
            "gross_return_sharpe": float(sealed["gross_return_sharpe"]),
            "net_return_10bp_sharpe": float(sealed["net_return_10bp_sharpe"]),
            "gross_return_market_beta": float(sealed["gross_return_market_beta"]),
            "mean_rank_ic": float(sealed["mean_rank_ic"]),
            "days": int(float(sealed["days"])),
        }
    (out / "audit_vs_sealed.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    print(f"\nAUDIT 2024–2025: gross Sharpe {summary['gross_return_sharpe']:.4f}, "
          f"net@10bp {summary['net_return_10bp_sharpe']:.4f}, "
          f"beta {summary['gross_return_market_beta']:.4f}", flush=True)
    print(f"Wrote {out} (sealed reports/week6 untouched)", flush=True)
    return summary


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    steps = [reclean, rebuild_research_panel, rebuild_factor_panel, rebuild_exposures,
             rebuild_predictions, run_week2, run_week_modules, audit_2024_2025]
    parser.add_argument(
        "--from-step", type=int, default=1, choices=range(1, len(steps) + 1),
        help="Resume from step N (see module docstring)",
    )
    args = parser.parse_args()
    cap_duckdb_memory()
    write_readme()
    for step in steps[args.from_step - 1:]:
        step()
    print(f"\nDone. Pre-fix reports remain under {REPORTS_PRE}")
    print(f"Post-fix outputs under {POST}")


if __name__ == "__main__":
    main()
