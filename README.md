# Cross-Sectional Equity Alpha Research

An auditable, point-in-time CRSP research pipeline testing whether six
interpretable price/volume signals forecast 20-trading-day cross-sectional
returns after transaction costs, over 2005-2025, with 2024-2025 sealed until a
single final test.

## Status: complete, then corrected after review

All six weeks are done. The panel, six factors, ten walk-forward folds,
staggered-cohort portfolio engine, risk neutralisation, the locked final
specification and the sealed 2024-2025 test are all built, run and tested.

**Correction notice (2026-09-14 and 2026-09-15, four rounds).** Four rounds of
external review found eighteen accounting, data and statistical defects after
the sealed run (`reports/project_review_2026-09-14.md`,
`reports/project_followup_review_2026-09-15.md`,
`reports/project_round3_review_2026-09-15.md`,
`reports/project_round4_review_2026-09-15.md`; a prior version of this notice
said nineteen -- 9+5+2+2 is 18, an arithmetic slip caught in round 4). All
eighteen were fixed and the whole pipeline was recomputed from the raw export
under the *unchanged* locked specification into `reports/post_fix/`. The
original sealed artefacts under `reports/week6/` are untouched and remain the
one-shot record; the recomputation is a **correction audit** of the same book
on the same, already-seen period, not a second sealed test. Both versions are
reported, labelled, everywhere below. The corrected figures are the ones to
quote.

| locked book `drop_rmom_120_20__neutral__decile` | original record | corrected audit |
|---|---:|---:|
| 2024-2025 gross Sharpe (HAC t) | 1.52 (2.76) | **1.43 (2.71)** |
| 2024-2025 net Sharpe at 10 bp (HAC t) | 1.22 | **1.06 (2.01)** |
| 2024-2025 realised market beta | -0.065 | **-0.063** |
| 2024-2025 breakeven cost | 49.7 bp | **38.5 bp** |
| 2024-2025 annual turnover | 8.9x | **10.4x** |
| 2014-2023 gross Sharpe (HAC t) | 0.53 (1.65) | **0.49 (1.53)** |
| 2014-2023 net Sharpe at 10 bp | 0.24 | **0.14** |
| 2014-2023 breakeven cost | 18.0 bp | **13.8 bp** |

What moved the numbers, in order of size: trading is now charged against
holdings drifted by the previous day's returns rather than against yesterday's
targets (turnover up, breakeven down); the daily IC series is sorted before its
Newey-West statistic; formation no longer conditions on a stock's future target
being observable; eligibility is decided at the close of t-1; the cleaner keeps
every common-share row so held names keep being marked; and delisting returns
are paid where the export records them. Round 3's two fixes (below) barely
move the headline -- they correct accounting integrity, not the book's
dominant return drivers.

**One correction I got wrong the first time**, worth stating plainly: I
reported that the raw export contained no delisting returns. It contains
11,824 rows flagged `DlyDelFlg = 'Y'`, 11,445 with a return. My scan missed
them because I conditioned it on the same common-share identity screen that
excluded them from the panel, so it confirmed its own premise. The follow-up
review found them by scanning without that filter, with a held position as the
worked example. The cleaner now keeps one event row per delisted security it
already knows.

**A third review then found the ingestion fix was incomplete on the portfolio
side.** The engine recognised an event's return correctly but had no state
transition afterward: a delisted name kept its stale pre-event target weight,
and the drift-aware trade math tried to "restore" it -- after a total loss this
read as repurchasing a wiped-out security. 99.48% of the missing-return
exposure I had just reported as a residual, disclosed limitation turned out to
be exactly this: retained equity in already-settled names, not unresolved
data. A name is now settled to cash the day after its event, with a single
correctly-sized exit trade and no equity exposure afterward:

| | round 2 (ingested, not settled) | round 3 (settled) |
|---|---:|---:|
| positions with no return, per day | 7.01 | **0.008** |
| gross weight with no return, per day | 0.51% of NAV | **0.0007%** |
| max gross weight with no return | 2.19% | **0.20%** |

The same review found the companion execution-timing diagnostic was checking
the wrong day: a trade on row *d* executes at the close of *d*-1, and the
diagnostic filtered on *d*'s return instead. Fixed alongside settlement, the
fraction of traded notional with no return recorded on its execution date
falls from 0.62% to 0.002%.

**A fourth review then checked the settlement fix itself and found two more
narrow issues, both disclosure rather than behaviour.** First: settlement
applies whether or not the event's own return is known, and treating a NULL
event return as a par (0%) payoff is a modelling assumption, not an observed
fact -- it affects one short position in the locked 2024-2025 book, 0.056% of
NAV, now measured and reported separately as `gross_unknown_event_payoff`
rather than folded silently into ordinary settlement. Second: the 0.002%
execution diagnostic checks only whether CRSP recorded a *return* on the
trade's execution date -- it says nothing about price, trading status, or
whether a flow is a cash settlement, and a retained delisting row is exactly a
case with a known return and no tradable price. Renamed
`traded_missing_execution_return` to say only what it measures.

**The result, stated at the width the evidence supports:**

> A frozen five-factor specification produced positive, nominally significant
> returns in its single 2024-2025 held-out test, including after modelled
> transaction costs: gross Sharpe 1.43 (HAC t 2.71), net Sharpe at 10 bp 1.06
> (HAC t 2.01), realised market beta -0.063 -- on the corrected accounting.

It does **not** establish durable or deployable alpha. The sealed test covers
two years only, and the cost model omits borrow cost, market impact, short
availability and capacity. The residual missing-return and unobserved-execution
exposures are now genuinely small (0.0007% and 0.002% respectively) once
delisted names are settled to cash rather than left as stale equity. Weeks 2-5
found essentially nothing distinguishable from zero
-- one specification then survived a fair test once. That is the honest summary
of the whole project, and the point of building it this way.

### Headline findings along the way (corrected figures)

- Of the six signals, `rvol_20` (NW t -2.85) and, after correction, `vs_20`
  (2.73) survive a Bonferroni correction on their information coefficient; no
  single factor is tradable after realistic costs.
- Fitted OLS, Ridge and gradient-boosting models never beat an equal-weighted
  composite of the six pre-registered signs *net of costs* (composite +0.13 at
  10 bp; the best model book, `gbm__decile`, -0.02), though on gross Sharpe
  `gbm__decile` now edges it (0.31 against 0.28, both HAC t about 1.0). Every
  Week 3-4 book sits within about one standard error of zero. The models' rank
  IC is significant at NW t about 2.0-2.3, not the 7.7-8.8 originally reported:
  that figure came from a daily series that was never sorted by date before
  its HAC statistic.
- Risk neutralisation (sector, beta, size) fails its pre-declared test in 7 of
  8 books, before and after correction: it halves annualised volatility while
  trading costs stay flat, so a fixed dollar cost doubles its bite on net
  Sharpe. The one book that passes both legs is the decile-weighted composite
  -- neutralising it *improves* net Sharpe at 10 bp from 0.115 (raw) to 0.130,
  while cutting beta from -0.270 to -0.056. Every other book, including the
  raw composite itself, fails.
- The final specification was locked by a rule declared before any Week 5
  result existed, applied mechanically to a 40-book candidate grid (20 of
  which pass the beta constraint). The winner is the maximum of correlated
  estimates, not a significance pick -- the runner-up has a higher in-sample
  HAC t. The lock was not re-selected after the corrections: the grid it was
  chosen from is the original record, and re-choosing after seeing 2024-2025
  would not be a lock.

See `reports/week6_final_memo.md` for the full result and its caveats,
`reports/week5_neutralisation_memo.md` for the neutralisation and lock
mechanics, and `PROGRESS.md` for the week-by-week record.

## Governance: how the seal works

This project's distinguishing feature is that its final test could not be
gamed after the fact. Four pieces enforce that:

1. **Pre-registration.** Every experiment's hypothesis, method and (for Week 5)
   success criterion is written into `experiments.csv` before the result
   exists; results are appended as new rows, never overwritten.
2. **A locked specification file.** `reports/week5/locked_specification.json`
   freezes the winning book (factors, signs, neutralisation, weighting, hold
   days, cap) plus the git commit it was locked at.
3. **A frozen, self-checking runner.** `src/evaluation/week6_final.py` reads
   the lock at runtime, hardcodes no book, and refuses to run if a required
   field is missing, a factor's sign disagrees with the pre-registered
   `FACTOR_SIGN`, the recorded commit is not an ancestor of `HEAD`, the
   runner's own content at that commit doesn't match what's executing, the
   `src/` tree at `HEAD` differs from the tree at the recorded commit, or
   `src/` has uncommitted changes on the sealed path. What this does *not*
   authenticate: the generated data panels and the package versions. The
   guarantee is "the committed research source is the locked one", no more.
   (The `src/` tree check was added after the sealed run; commits `fbbe574`
   and `084f5eb` share tree `268447d8`, so it would have passed.)
   The lock file itself is immutable by default: rerunning `week5_lock.py`
   writes its selection to `reports/week5/reselection.json` unless `--relock`
   is passed. A delisted name is settled to cash the day after its event
   (`daily_book`'s "Event settlement"), not left as stale tradable equity, and
   an unknown (NULL) event return is settled as a disclosed zero-return
   assumption rather than silently treated as a verified payoff.
4. **A one-shot marker.** Reaching the sealed period requires typing the
   literal string `run-sealed-2024-2025-exactly-once`; there is no default
   argument that reaches it. An atomic `O_CREAT|O_EXCL` marker file,
   `reports/week6/sealed_run_started.json`, is written the instant the sealed
   period is opened and is never removed. **The sealed run has already
   happened -- do not run `week6_final.py` in sealed mode again; the code
   itself will refuse, but don't try.**

## Reproduction

### Prerequisite: raw data

The pipeline needs the raw CRSP export, which is **not versioned** (excluded
via `.gitignore`; see `data_manifest.md`). Place it at
`crsp/yb8xejbnpiflaprb.csv` and do not edit it.

### Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Two reproducible versions

There are two named versions of every result, and they are reproduced
differently:

- **Original record** (tag `project-1-complete`, everything under `reports/`
  except `reports/post_fix/`): the pre-correction pipeline and the sealed
  one-shot test. Reproduce it with `git checkout project-1-complete` and the
  stage list below; `week6_final.py replay` there checks against the numbers
  recorded in the lock.
- **Correction audit** (`reports/post_fix/`, current `HEAD`): the same locked
  specification recomputed after the 2026-09-14 review fixes. Reproduce it
  with one command, which rebuilds from the raw export through the 2024-2025
  audit and never touches `reports/week6/`:

  ```powershell
  python -m src.evaluation.run_post_fix_audit
  python src/evaluation/week6_final.py replay reports/post_fix/week5/replay_targets.json
  ```

  The second line proves the current runner reproduces the corrected
  2014-2023 figures for the locked book, writing its validation next to the
  targets file, never into `reports/week6/`. Running `replay` with no argument
  on corrected source fails by design: it compares against the original lock's
  numbers, which the corrected engine no longer produces.
  `reports/post_fix_2026-09-14/` is a pruned snapshot of the first correction
  audit, superseded after the 2026-09-15 follow-up review.

### Pipeline stages, in order

Each stage reads only what an earlier stage wrote. **These commands write into
the historical report locations** (`reports/week2`-style factor folders,
`reports/week3` .. `reports/week5`) and are the original stage-by-stage
workflow; run them only on a checkout of `project-1-complete` if you want to
regenerate the original record. To rebuild the *current* version use
`run_post_fix_audit`, which routes every output under `reports/post_fix/`.

```powershell
# Week 1: ingest and build the point-in-time panel
python src/data/clean_crsp.py
python src/data/build_research_panel.py

# Week 2-3: factors, evaluation, baseline portfolio
python src/features/build_factor_panel.py
python src/evaluation/factor_eval.py
python src/evaluation/week3_baseline.py

# Week 4: walk-forward models
python src/models/walk_forward.py
python src/evaluation/week4_models.py

# Week 5: risk exposures, neutralisation, robustness, the lock
python src/features/exposures.py
python src/evaluation/week5_robustness.py
python src/evaluation/week5_neutral.py
python src/evaluation/week5_ablation_neutral.py
python src/evaluation/week5_lock.py     # writes reselection.json; the lock is immutable

# Reporting
python src/reporting/final_figures.py
```

`reports/final_report.pdf` is a rendered copy of `reports/final_report.md`
(figures embedded), built with `src/reporting/render_pdf.py`. It needs two
packages not in `requirements.txt` because they are presentation-only and not
part of the research pipeline -- `pip install markdown xhtml2pdf` -- then
`python src/reporting/render_pdf.py`. The PDF is checked in so a reader does not
need that toolchain just to view the result.

Notes:

- `clean_crsp.py` writes a year-partitioned daily panel to
  `data/processed/crsp_daily_panel/` and a validation summary to
  `data/processed/cleaning_validation.csv`.
- `clean_crsp.py` keeps every US common-share row plus each such security's
  delisting event row (`DlyDelFlg = 'Y'`, placeholder classifications);
  exchange, issuer, conditional-type and trading-status screens are entry
  eligibility, not row filters, so held names keep being marked after a
  status change and are paid their delisting return.
- `build_research_panel.py` applies the locked point-in-time investability
  screen, decided at the close of t-1, and writes the eligible-universe /
  20-trading-day-target panel to `data/processed/research_panel/`.
- `exposures.py` needs both the cleaned panel and the factor panel to already
  exist (it checks for both and exits with a clear message if either is
  missing), so it cannot move earlier than `build_factor_panel.py`. It sits
  here, ahead of `week5_neutral.py`, because that is the first stage that
  consumes it -- Weeks 2-4 never read it.
- `factor_eval.py` optionally takes factor names as arguments (default: all
  six).
- Model fitting, prediction and portfolio cohort formation all stop on
  2023-11-30; P&L is marked through 2023-12-29 so the last cohorts formed
  still finish their 20-day hold. `exposures.py` is the one exception: it
  builds beta/size/sector over the full panel history because the rolling
  beta needs that history, so it does read 2024-2025 *covariates*, and an
  early audit summary briefly inspected them (see the disclosure in
  `reports/week5_neutralisation_memo.md`, section 11). No 2024-2025 return,
  target, or performance result was computed or evaluated before Week 6 --
  the sealed period's outcomes are opened only once, there.

### Week 6: the sealed final test and how to verify it

**Do not run `src/evaluation/week6_final.py` in sealed mode.** It has already
been run, exactly once, on 2026-09-11 at commit `084f5eb`, against the
specification locked at `fbbe574`. The one-shot marker
(`reports/week6/sealed_run_started.json`) and the final artifacts already
exist; the runner refuses to repeat it.

What you *can* and should run is the replay:

```powershell
python src/evaluation/week6_final.py replay
```

This re-runs the identical code path over 2014-01-02..2023-11-30 (P&L to
2023-12-29) and asserts that it reproduces the recorded Week 5 figures for the
locked book to about `1e-15`. It reads no 2024-2025 data. This is how you
verify the final-test machinery is correct without touching the seal. On the
corrected source, pass `reports/post_fix/week5/replay_targets.json` as the
second argument (see "Two reproducible versions").

Running the module with any other argument (including no argument) exits
immediately with a usage message, before any date is chosen -- there is no
accidental path into the sealed period.

### Tests

```powershell
python -m pytest -q
```

101 tests, a few seconds. They run against synthetic frames and do not need any
built panel, so this works even without the raw data present.
`python reports/review_checks.py` runs the reviewer's four synthetic
reproductions from 2026-09-14, now asserting the corrected behaviour.

## Where to read the results

- `reports/project_review_2026-09-14.md`,
  `reports/project_followup_review_2026-09-15.md`,
  `reports/project_round3_review_2026-09-15.md` and
  `reports/project_round4_review_2026-09-15.md` -- the four external reviews
  that found the eighteen defects; `reports/post_fix/` -- the corrected
  recomputation (weeks 2-5, the 2024-2025 audit, and `figures/`);
  `reports/final_report.md` section 0 -- what changed and by how much.
- `reports/week6_final_memo.md` -- the original sealed result as recorded, its
  precision, and what it does and does not establish.
- `reports/week5_neutralisation_memo.md`, `reports/week4_model_memo.md`,
  `reports/week3_baseline_memo.md`, `reports/factor_memo_week2.md` -- the
  weekly trail of findings that led there.
- `experiments.csv` -- the pre-registration and result log: every hypothesis
  and success criterion, written before the result existed, with results
  appended as separate rows.
- `PROGRESS.md` -- the running, narrative status record.

## Project layout

```text
config/          locked parameters as work starts
data/            local generated data only (not versioned)
src/data/        ingestion and validation
src/features/    factor definitions, the aligned rank panel, risk exposures
src/models/      walk-forward splits and model fitting
src/portfolio/   the staggered-cohort backtest engine
src/evaluation/  factor, baseline, model, neutralisation, lock and final-test drivers
src/reporting/   final report figures
tests/           checks for critical transformations (synthetic data, no built panel needed)
reports/         weekly memos, the final memo, locked specification, sealed-run artifacts
notebooks/       exploratory analysis only
```

`experiments.csv` and the locked specification are the source of truth for
research choices; this README summarises them.
