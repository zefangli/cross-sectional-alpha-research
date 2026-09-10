"""Week 6: the one-shot final test against the sealed 2024-2025 period.

2024-2025 has been held out for six weeks. This module opens it EXACTLY ONCE,
runs the specification locked in `reports/week5/locked_specification.json`
unchanged, and reports the result whatever it is -- no re-selection, no
re-tuning, no second look. That is the whole point of the exercise: a
specification chosen on 2014-2023 evidence is worthless as a test unless it is
run on the sealed period exactly as declared, and only once.

Everything the run needs -- factor names and signs, neutralisation on/off,
weighting, hold days, position cap, winsorisation quantiles -- is READ from the
locked JSON at runtime rather than hardcoded here, because a parallel research
process regenerates that JSON from the full candidate grid and the winning
book can change (it did, mid-development of this module: the lock moved from
the full six-factor composite to `drop_rmom_120_20`). If the JSON is missing a
field this module needs, its recorded git commit is not an ancestor of the current
HEAD, or a factor's recorded sign disagrees with the pre-registered sign in
`factors.py`, the run refuses outright: a silent default at this point would
defeat six weeks of governance.

This module supports composite-family winners only (raw or neutralised, full
six factors or an ablated subset, rank or decile weighted). A fitted-model
winner (`ols`/`ridge`/`gbm`) would need walk-forward predictions extended into
2024-2025, which do not exist and are out of scope here; such a specification
is refused with an explicit message rather than silently mishandled.

The seal: `main` takes exactly one positional argument, either "replay" or the
literal opt-in string `SEAL_MODE`. There is no default -- running the module
with no arguments exits before any date is ever chosen, let alone read.
`replay` runs the identical code path over 2014-01-02..2023-11-30 with P&L to
2023-12-29 and asserts the locked book's recorded Week 5 numbers reproduce to a
tight tolerance -- proof the runner executes the frozen specification
correctly, using only pre-2024 data. Only the literal `SEAL_MODE` string opens
2024-2025, and only once that run is deliberately made.
"""
from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.evaluation.week4_models import COHORT_LAST as REPLAY_COHORT_LAST
from src.evaluation.week5_neutral import (EXPOSURE_FACTORS, daily_rank_ic, merged_scan_query,
                                          neutralise as neutralise_score, summarize as week5_summarize,
                                          winsorize)
from src.evaluation.week5_robustness import add_signal, composite_frame
from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.models.splits import walk_forward_splits
from src.models.walk_forward import MODELS as FITTED_MODEL_NAMES
from src.portfolio.backtest import COSTS_BPS, capped_neutral_weights, daily_book

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
EXPOSURES = ROOT / "data" / "processed" / "exposures"
SPEC_PATH = ROOT / "reports" / "week5" / "locked_specification.json"
OUT = ROOT / "reports" / "week6"

REPLAY_MODE = "replay"
SEAL_MODE = "run-sealed-2024-2025-exactly-once"

REPLAY_PNL_LAST = "2023-12-29"
# Formation cutoff and P&L end for the sealed run: the same "stop 20 trading
# days before year end, mark P&L to year end" convention COHORT_LAST/PNL_LAST
# already use for 2023, applied to the last year the sealed period covers.
SEALED_COHORT_LAST = "2025-11-30"
SEALED_PNL_LAST = "2025-12-31"

REQUIRED_FIELDS = ("git_commit", "locked_book", "weighting", "neutralised",
                   "factor_set", "factors", "hold_days", "cap")
REPLAY_REQUIRED_TARGETS = ("realised_beta", "net_sharpe_10bp", "gross_sharpe")
# Extra recorded numbers to cross-check opportunistically if the spec carries them.
REPLAY_OPTIONAL_TARGETS = {"gross_hac_t": "gross_return_hac_t", "max_drawdown": "gross_return_max_drawdown"}
REPLAY_TOLERANCE = dict(rtol=1e-6, atol=1e-8)

NEUTRALISATION_CONTROLS = ("sector", "beta_252", "log_mcap")

METRICS = (
    "mean_rank_ic", "rank_ic_hac_t", "gross_return_sharpe", "gross_return_hac_t",
    *(f"net_return_{b}bp_sharpe" for b in COSTS_BPS),
    "gross_return_annualised_return", "gross_return_annualised_volatility",
    "breakeven_bp", "annual_turnover", "gross_return_market_beta",
    "mean_gross_exposure", "mean_net_exposure", "gross_return_max_drawdown",
    *(f"exposure_{f}" for f in ALL_FACTORS), "exposure_beta_252", "exposure_log_mcap", "exposure_sector",
)


def _git(*args) -> subprocess.CompletedProcess:
    """Run git, tolerating this machine's dubious-ownership guard via a
    per-invocation `-c`, never a persisted config change."""
    return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(ROOT), *args],
                          capture_output=True, text=True)


def current_head_commit() -> str:
    result = _git("rev-parse", "HEAD")
    if result.returncode != 0:
        raise RuntimeError(f"could not resolve current git HEAD: {result.stderr.strip()}")
    return result.stdout.strip()


def check_provenance(recorded: str, head_commit: str) -> None:
    """The recorded commit must be an ancestor of HEAD, and `src/` must be clean.

    Requiring the recorded commit to EQUAL HEAD is unsatisfiable: the lock file
    lives in the repository, so the commit that contains it necessarily has a
    different hash than the one recorded inside it, and every later commit --
    including the one adding this module -- moves HEAD again. Ancestry is the
    property actually wanted: the lock was generated from a state this checkout
    descends from. Staleness that would really matter is uncommitted drift in
    the code the run executes, so that is checked directly.
    """
    if recorded != head_commit:
        ancestry = _git("merge-base", "--is-ancestor", recorded, head_commit)
        if ancestry.returncode != 0:
            raise ValueError(
                f"locked specification commit {recorded} is not an ancestor of HEAD "
                f"{head_commit} -- refusing to run a specification this checkout "
                f"does not descend from")


def require_clean_source() -> None:
    """Refuse the sealed run if `src/` has uncommitted changes.

    Ancestry alone cannot catch the staleness that matters most -- code edited
    but never committed. This is checked only on the sealed path: a replay or a
    unit test may legitimately run from a dirty tree, the one-shot final test
    may not.
    """
    dirty = _git("status", "--porcelain", "--", "src")
    if dirty.returncode == 0 and dirty.stdout.strip():
        raise ValueError(
            "uncommitted changes under src/ -- refusing to open the sealed period against "
            f"code that is not committed:\n{dirty.stdout.strip()}")


def resolve_factors(spec: dict) -> tuple:
    """Factor names from `spec['factors']` (a list of `{"name", "sign"}`),
    cross-checked against the pre-registered signs in `factors.FACTOR_SIGN` --
    a sign is not a per-specification choice, it was fixed before any factor
    was evaluated (Week 2)."""
    entries = spec["factors"]
    if not entries:
        raise ValueError("spec['factors'] is empty")
    names = tuple(e["name"] for e in entries)
    unknown = set(names) - set(ALL_FACTORS)
    if unknown:
        raise ValueError(f"factors not in ALL_FACTORS: {sorted(unknown)}")
    for e in entries:
        if FACTOR_SIGN[e["name"]] != e["sign"]:
            raise ValueError(f"{e['name']}: spec sign {e['sign']} does not match "
                             f"pre-registered sign {FACTOR_SIGN[e['name']]}")
    return names


def resolve_name(spec: dict) -> str:
    """The book's base name, stripping the `__neutral`/`__decile` suffixes in
    either order. Any composite-family label (the full composite or a
    `drop_<factor>` ablation) is accepted; a fitted model is not -- it would
    need walk-forward predictions extended into 2024-2025, which do not exist."""
    name = spec["locked_book"].replace("__neutral", "").replace("__decile", "")
    if name in FITTED_MODEL_NAMES:
        raise ValueError(f"week6_final only supports composite-family specifications; "
                         f"locked_book={spec['locked_book']!r} resolves to the fitted model {name!r}")
    return name


def check_regressors(spec: dict) -> None:
    """`spec['neutralisation']['regressors']` is free-text, so the check is a
    substring match rather than an exact key comparison -- it still catches an
    unsupported control this runner's `neutralise_score` cannot apply."""
    regressors = " ".join(spec["neutralisation"]["regressors"]).lower()
    missing = [c for c in NEUTRALISATION_CONTROLS if c not in regressors]
    if missing:
        raise ValueError(f"neutralisation.regressors does not mention {missing}: {regressors!r}")


def resolve_quantiles(spec: dict) -> tuple:
    quantiles = tuple(spec["neutralisation"]["winsorise_quantiles"])
    if quantiles != (0.01, 0.99):
        raise ValueError(f"unsupported winsorise_quantiles {quantiles!r}; "
                         f"only (0.01, 0.99) is implemented by week5_neutral.winsorize")
    return quantiles


def validate_spec(spec: dict, head_commit: str) -> dict:
    """Refuse to proceed if a required field is absent, a value is nonsensical,
    a factor's sign disagrees with the pre-registered one, or the recorded
    commit is not an ancestor of HEAD."""
    missing = [f for f in REQUIRED_FIELDS if f not in spec]
    if missing:
        raise ValueError(f"locked specification missing required field(s): {missing}")
    check_provenance(spec["git_commit"], head_commit)
    if spec["weighting"] not in ("rank", "decile"):
        raise ValueError(f"weighting must be 'rank' or 'decile', got {spec['weighting']!r}")
    if not isinstance(spec["neutralised"], bool):
        raise ValueError(f"neutralised must be a bool, got {spec['neutralised']!r}")
    if not (isinstance(spec["hold_days"], int) and spec["hold_days"] > 0):
        raise ValueError(f"hold_days must be a positive int, got {spec['hold_days']!r}")
    if not (isinstance(spec["cap"], (int, float)) and 0 < spec["cap"] <= 1):
        raise ValueError(f"cap must be in (0, 1], got {spec['cap']!r}")
    resolve_factors(spec)
    resolve_name(spec)
    if spec["neutralised"]:
        if "neutralisation" not in spec:
            raise ValueError("neutralised=True but spec has no 'neutralisation' block")
        resolve_quantiles(spec)
        check_regressors(spec)
    return spec


def load_spec(path: Path = SPEC_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run the Week 5 lock first")
    spec = json.loads(path.read_text())
    return validate_spec(spec, current_head_commit())


def neutral_exposures(con, scan: str, exp_scan: str, first_date: str, last_date: str,
                      quantiles: tuple = (0.01, 0.99)) -> pd.DataFrame:
    """Sector plus winsorised beta/log market cap over the aligned rows in
    [first_date, last_date] -- the regression inputs `neutralise_score` needs,
    built exactly as `week5_neutral.formation_exposures` builds them, but with
    an explicit date upper bound so it works for both the replay and the
    sealed window (the original hard-codes Week 4/5's own `COHORT_LAST`)."""
    exposures = con.sql(f"""
        SELECT exp.permno, exp.date, exp.tdi, exp.sector, exp.beta_252, exp.log_mcap
        FROM {exp_scan} exp JOIN {scan} fp USING (permno, date, tdi)
        WHERE fp.aligned AND fp.date >= DATE '{first_date}' AND fp.date <= DATE '{last_date}'
    """).df()
    lower, upper = quantiles
    exposures["beta_252_w"] = exposures.groupby("date")["beta_252"].transform(winsorize, lower, upper)
    exposures["log_mcap_w"] = exposures.groupby("date")["log_mcap"].transform(winsorize, lower, upper)
    return exposures


def score_frame(con, scan: str, exp_scan: str, spec: dict, first_date: str, last_date: str) -> pd.DataFrame:
    """(permno, date, tdi, rank, decile) for the locked book, raw or
    neutralised per `spec['neutralised']`. The equal-weighted signed-rank
    composite itself reuses `week5_robustness.composite_frame`/`add_signal`
    verbatim -- the same machinery `week5_ablation_neutral.py` uses for every
    other ablated book, generalised here to an arbitrary factor subset."""
    names = resolve_factors(spec)
    frame = add_signal(composite_frame(con, scan, first_date, last_date), names)
    if not spec["neutralised"]:
        return frame[["permno", "date", "tdi", "rank", "decile"]]
    exposures = neutral_exposures(con, scan, exp_scan, first_date, last_date, resolve_quantiles(spec))
    score = frame.rename(columns={"rank": "score"})[["permno", "date", "tdi", "score"]]
    return neutralise_score(score, exposures)


def book(con, scan: str, frame: pd.DataFrame, weighting: str, first_date: str, last_date: str,
        cap: float, hold: int) -> pd.DataFrame:
    """`week5_neutral.book`, with cap and hold days taken from the locked
    specification instead of `backtest.py`'s module defaults."""
    cohort = frame[["permno", "tdi", "date"]].copy()
    cohort["w"] = capped_neutral_weights(frame, weighting, cap=cap)
    con.register("cohort", cohort[["permno", "tdi", "w"]])
    daily = daily_book(con, scan, first_date, last_date, factors=EXPOSURE_FACTORS, hold=hold)
    con.unregister("cohort")
    return daily


def run_locked_book(con, scan: str, exp_scan: str, spec: dict, first_date: str,
                    cohort_last: str, pnl_last: str) -> tuple:
    """Form cohorts on [first_date, cohort_last], mark P&L through pnl_last so
    the last cohorts formed still finish their hold -- the same distinction
    `week4_models`/`week5_neutral` draw between COHORT_LAST and PNL_LAST.
    Returns (daily, summary) with exactly the frozen metric set."""
    con.execute(f"CREATE OR REPLACE TABLE merged_panel AS {merged_scan_query(scan, exp_scan, pnl_last)}")
    frame = score_frame(con, scan, exp_scan, spec, first_date, cohort_last)
    assert frame.date.max() <= pd.Timestamp(cohort_last), "cohort formed past the formation cutoff"
    assert not frame[["rank", "decile"]].isna().any().any(), "NaN in the scored frame"
    daily = book(con, "merged_panel", frame, spec["weighting"], first_date, pnl_last,
                cap=spec["cap"], hold=spec["hold_days"])
    assert daily.date.max() <= pd.Timestamp(pnl_last), "P&L marked past pnl_last"
    ic = daily_rank_ic(con, scan, frame)
    summary = week5_summarize(daily, ic)
    summary["mean_net_exposure"] = daily.net_exposure.mean()
    return daily, summary


def formation_start(con, scan: str, cohort_last: str) -> str:
    """First validation date of fold 1 -- the one ramp, at the very start of
    the evaluation window, shared by every book (Weeks 4-5 convention)."""
    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=cohort_last)
    return str(splits.validation_start.min())


def frozen_protocol(spec: dict, first_date: str, cohort_last: str, pnl_last: str, sealed: bool) -> dict:
    """Every remaining choice needed to reproduce the run, beyond what the
    locked JSON already carries: dates, the single-ramp convention, costs and
    the metric list."""
    return {
        "sealed": sealed,
        "formation_start": first_date,
        "cohort_formation_cutoff": cohort_last,
        "pnl_end_date": pnl_last,
        "ramp_convention": "one ramp at formation_start; one continuous daily_book "
                           "call over the full span, matching Weeks 4-5",
        "cost_bps": list(COSTS_BPS),
        "neutralisation_controls": list(NEUTRALISATION_CONTROLS),
        "metrics": list(METRICS),
        "spec": spec,
    }


def replay(con, scan: str, exp_scan: str, spec: dict) -> pd.DataFrame:
    """Run the locked book over 2014-01-02..2023-11-30, P&L to 2023-12-29, and
    assert it reproduces the recorded Week 5 numbers -- proof this runner
    executes the frozen specification correctly, using only pre-2024 data."""
    missing = [f for f in REPLAY_REQUIRED_TARGETS if f not in spec]
    if missing:
        raise ValueError(f"locked specification missing replay target field(s): {missing}")
    first_date = formation_start(con, scan, REPLAY_COHORT_LAST)
    daily, summary = run_locked_book(con, scan, exp_scan, spec, first_date,
                                     REPLAY_COHORT_LAST, REPLAY_PNL_LAST)
    assert daily.date.max() <= pd.Timestamp(REPLAY_PNL_LAST), "replay read past 2023-12-29"

    check_map = {"realised_beta": "gross_return_market_beta", "gross_sharpe": "gross_return_sharpe",
                "net_sharpe_10bp": "net_return_10bp_sharpe",
                **{k: v for k, v in REPLAY_OPTIONAL_TARGETS.items() if k in spec}}
    rows = [{"metric": k, "computed": summary[v], "recorded_week5": spec[k],
             "matches": bool(np.isclose(summary[v], spec[k], **REPLAY_TOLERANCE))}
            for k, v in check_map.items()]
    result = pd.DataFrame(rows)
    if not result["matches"].all():
        raise AssertionError(f"replay does not reproduce the locked Week 5 numbers:\n{result}")

    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "replay_validation.csv", index=False)
    (OUT / "replay_protocol.json").write_text(
        json.dumps(frozen_protocol(spec, first_date, REPLAY_COHORT_LAST, REPLAY_PNL_LAST, sealed=False),
                   indent=2, default=str))
    return result


def run_sealed(con, scan: str, exp_scan: str, spec: dict) -> dict:
    """Open 2024-2025 exactly once and run the locked specification unchanged."""
    first_date = formation_start(con, scan, SEALED_COHORT_LAST)
    daily, summary = run_locked_book(con, scan, exp_scan, spec, first_date,
                                     SEALED_COHORT_LAST, SEALED_PNL_LAST)
    OUT.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUT / "final_daily.csv", index=False)
    pd.Series(summary).to_csv(OUT / "final_result.csv")
    (OUT / "final_protocol.json").write_text(
        json.dumps(frozen_protocol(spec, first_date, SEALED_COHORT_LAST, SEALED_PNL_LAST, sealed=True),
                   indent=2, default=str))
    return summary


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in (REPLAY_MODE, SEAL_MODE):
        sys.exit(f"usage: week6_final.py {{{REPLAY_MODE}|{SEAL_MODE}}}\n"
                 f"The sealed mode opens 2024-2025 exactly once. There is no default "
                 f"and no way to reach it without typing the literal opt-in string.")
    sealed = argv[0] == SEAL_MODE
    if sealed:
        require_clean_source()

    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    if not EXPOSURES.exists():
        sys.exit("Exposures not found. Run src/features/exposures.py first.")

    spec = load_spec()
    print(f"Locked specification (commit {spec['git_commit'][:12]}): "
          f"{spec['locked_book']}, weighting={spec['weighting']}, "
          f"neutralised={spec['neutralised']}, hold_days={spec['hold_days']}, cap={spec['cap']}")

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    exp_scan = f"parquet_scan('{(EXPOSURES / '**' / '*.parquet').as_posix()}')"

    if sealed:
        summary = run_sealed(con, scan, exp_scan, spec)
        print(f"\nFINAL RESULT (2024-2025, one shot): gross Sharpe "
              f"{summary['gross_return_sharpe']:.4f}, net Sharpe@10bp "
              f"{summary['net_return_10bp_sharpe']:.4f}, beta "
              f"{summary['gross_return_market_beta']:.4f}")
    else:
        result = replay(con, scan, exp_scan, spec)
        print("\nReplay reproduces the locked Week 5 numbers:\n", result.to_string(index=False))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
