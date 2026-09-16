# Cross-Sectional Equity Alpha Research

An auditable, point-in-time CRSP research pipeline that asks one question:

> **Do six interpretable price and volume signals forecast 20-trading-day
> cross-sectional equity returns well enough to trade after costs?**

US equities, 2005–2025. The 2024–2025 window was sealed from the outset and
opened exactly once, against a specification frozen in a committed file before
anyone looked. Every hypothesis was written down before its result existed.

The honest answer is **a weak signal that survived a fair test once** — and the
project is built so you can check that claim rather than take it on trust.

---

## Result

A frozen five-factor specification, tested once on the sealed 2024–2025 period:

| metric | value |
|---|---|
| gross Sharpe | 1.43 (Newey–West *t* = 2.71) |
| net Sharpe @ 10 bp | 1.06 (*t* = 2.01) |
| breakeven cost | 38.5 bp |
| realised market beta | −0.063 |
| max drawdown | 3.6% |
| period | 501 trading days |

**Read these numbers narrowly.**

- They are a **post-correction recomputation** of the unchanged locked
  specification over the already-seen 2024–2025 period — *not* a second sealed
  test. The seal was opened once, under the pipeline as it then stood; that
  run's own numbers are preserved untouched in `reports/week6/`. A
  recomputation on seen data is weaker evidence than the original one-shot run.
- The HAC 95% interval on the Sharpe is **[0.40, 2.46]**. The magnitude is
  barely pinned down; using 1.43 as a forward expectation is unsupported.
- Two years is one regime, and the result is **not statistically distinguishable**
  from the much weaker selection-sample estimate (difference *t* ≈ 1.5).
- The cost model is a flat per-notional charge. No borrow cost, no market
  impact, no short-availability constraint, no capacity analysis.

This does **not** establish durable or deployable alpha.

## What the research found

Most of it is nulls, and that is the point.

- **No single factor is tradable.** Of the six signals, only `rvol_20`
  (NW *t* −2.85) and `vs_20` (2.73) survive a Bonferroni correction on their
  information coefficient, and none clears realistic costs alone.
- **Fitted models never beat a flat composite net of costs.** OLS, Ridge and
  gradient boosting all lose to an equal-weighted composite of the six
  pre-registered signs (+0.13 net Sharpe at 10 bp against `gbm__decile`'s
  −0.04). The models' rank IC is significant (NW *t* ≈ 2.0–2.3); their net
  P&L is not — they trade more for less.
- **Risk neutralisation fails its pre-declared test in 7 of 8 books.** It
  halves volatility while trading costs stay flat, so a fixed dollar cost
  takes a much larger bite out of net Sharpe. The one book that passes both
  legs is the decile-weighted composite, where neutralising *improves* net
  Sharpe (0.115 → 0.130) while cutting beta from −0.270 to −0.056.
- **The winner was never distinguishable from its neighbours.** The final
  specification is the maximum of 20 correlated admissible candidates under a
  rule fixed in advance — not a significance pick. On the corrected selection
  sample a *different* book would rank first (0.157 against the locked book's
  0.136). The lock was kept anyway, because re-selecting after the seal was
  opened turns a pre-registered test into a fitted one. That the ranking flips
  under a bug fix is itself the finding: this was one draw from a cluster.

## How the seal works

The distinguishing feature of this project is that its final test could not be
gamed after the fact. Four mechanisms enforce that:

**1. Pre-registration.** Every experiment's hypothesis, method and success
criterion is written into `experiments.csv` *before* the result exists.
Results are appended as new rows, never overwritten.

**2. A locked specification file.** `reports/week5/locked_specification.json`
freezes the winning book — factors, signs, neutralisation, weighting, hold
days, position cap — plus the git commit it was locked at. It is immutable by
default: re-running the lock writes to `reselection.json` instead, unless
`--relock` is passed explicitly.

**3. A frozen, self-checking runner.** `src/evaluation/week6_final.py` reads
the lock at runtime and hardcodes no book. It refuses to run if a required
field is missing, a factor's sign disagrees with the pre-registered
`FACTOR_SIGN`, the recorded commit is not an ancestor of `HEAD`, the runner's
own content differs from that commit, the `src/` tree has drifted, or `src/`
has uncommitted changes on the sealed path.

> What this does **not** authenticate: the generated data panels and the
> package versions. The guarantee is *"the committed research source is the
> locked one"* — no more.

**4. A one-shot marker.** Reaching the sealed period requires typing the
literal string `run-sealed-2024-2025-exactly-once`; no default argument
reaches it. An atomic `O_CREAT|O_EXCL` marker file is written the instant the
seal is opened and is never removed.

> ⚠️ **The sealed run has already happened.** Do not run `week6_final.py` in
> sealed mode. The code will refuse — but don't try.

## Data

**Source: CRSP daily stock file, accessed via WRDS.**

CRSP data is licensed, and the license prohibits redistribution. **No CRSP
data — raw, cleaned, or derived — is published in this repository.** That
includes the raw export, the cleaned panel, the research panel, per-security
return series and index return series. All of it is excluded from version
control; `data_manifest.md` records the export's provenance, integrity rule
and column layout, but not its contents.

What *is* published is this project's own output: source code, tests,
pre-registration and result logs, portfolio-level summary statistics, memos
and figures. Reproducing the results requires your own CRSP/WRDS entitlement.

If you have one, place the export at `crsp/yb8xejbnpiflaprb.csv` and do not
edit it in place.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Rebuild every current result from the raw export in one command:

```powershell
python -m src.evaluation.run_post_fix_audit
python src/evaluation/week6_final.py replay reports/post_fix/week5/replay_targets.json
```

The second line proves the current runner reproduces the current selection-sample
figures for the locked book. It never touches `reports/week6/`.

Run the tests — they use synthetic frames, so they work without any data:

```powershell
python -m pytest -q          # 101 tests, a few seconds
python reports/review_checks.py
```

## Verifying the sealed test without breaking it

```powershell
python src/evaluation/week6_final.py replay
```

This re-runs the identical code path over 2014-01-02 … 2023-11-30 and asserts
it reproduces the recorded figures for the locked book to about `1e-15`. It
reads no 2024–2025 data. Any other argument — including none — exits with a
usage message before a single date is chosen. There is no accidental path into
the sealed period.

## Two reproducible versions

Every result exists in two named versions, reproduced differently:

| version | where | how |
|---|---|---|
| **Original record** | tag `project-1-complete`; all of `reports/` except `post_fix/` | `git checkout project-1-complete`, then the stage list in `doc.md`. Preserved unchanged because the sealed test cannot be re-run. |
| **Current** | `reports/post_fix/`, at `HEAD` | `python -m src.evaluation.run_post_fix_audit` |

## Where to read the results

| file | what it is |
|---|---|
| `reports/final_report.md` | the full consolidated report — start here |
| `reports/final_report.pdf` | the same, rendered with figures embedded |
| `reports/post_fix/` | current recomputed artifacts and `figures/` |
| `reports/week6_final_memo.md` | the original sealed result as recorded, and its limits |
| `experiments.csv` | the pre-registration log: hypotheses and success criteria, written before results |
| `data_manifest.md` | the raw export's provenance, integrity rule and delisting handling |
| `doc.md` | full engineering documentation, including stage-by-stage commands |

Topic memos covering the signal construction, baseline portfolios, model
comparison and neutralisation sit alongside these in `reports/`.

## Design notes

- **Point-in-time throughout.** Eligibility is decided at the close of *t−1*,
  so the cross-section is fully known before the close it trades at.
- **Delisting returns are ingested, not dropped.** In CRSP's CIZ format a
  delisting return is a `DlyRet` row flagged `DlyDelFlg='Y'` carrying
  placeholder classifications that fail an ordinary common-share screen. Those
  rows are retained, and a delisted name is settled to cash the day after its
  event — one correctly-sized exit trade, then zero exposure. An unknown
  (NULL) event return is disclosed as a zero-return *assumption*, never
  treated as a verified payoff.
- **Trading is drift-aware.** A daily-rebalanced book's real trade is target
  minus yesterday's *drifted* holding, not target minus yesterday's target.
- **The engine is a cost overlay, not a cash-reconciled simulator.** Stated
  plainly in `src/portfolio/backtest.py`'s module docstring.
- **Covariate leakage, disclosed.** Model fitting and cohort formation stop at
  2023-11-30. The one exception is `src/features/exposures.py`, which builds
  rolling beta/size/sector over full panel history and therefore reads
  2024–2025 *covariates*. No 2024–2025 return, target or performance figure
  was computed before the sealed run.

## Project layout

```text
config/          locked parameters, fixed as work started
data/            local generated data only (not versioned)
src/data/        ingestion, cleaning and validation
src/features/    factor definitions, the aligned rank panel, risk exposures
src/models/      walk-forward splits and model fitting
src/portfolio/   the staggered-cohort backtest engine
src/evaluation/  factor, baseline, model, neutralisation, lock and final-test drivers
src/reporting/   report figures and PDF rendering
tests/           synthetic-data checks for critical transformations
reports/         memos, locked specification, sealed-run artifacts, results
notebooks/       exploratory analysis only
```

`experiments.csv` and `reports/week5/locked_specification.json` are the source
of truth for research choices. This README summarises them.

---

*Data source: CRSP via WRDS, used under licence and **not redistributed**.
Code in `src/` and `tests/` is the author's own work. See [Data](#data).*
