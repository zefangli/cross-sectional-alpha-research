# Cross-Sectional Equity Alpha Research

An auditable, point-in-time CRSP research pipeline testing whether six
interpretable price/volume signals forecast 20-trading-day cross-sectional
returns after transaction costs, over 2005-2025, with 2024-2025 sealed until a
single final test.

## Status: complete

All six weeks are done. The panel, six factors, ten walk-forward folds,
staggered-cohort portfolio engine, risk neutralisation, the locked final
specification and the sealed 2024-2025 test are all built, run and tested.

**The result, stated at the width the evidence supports:**

> A frozen five-factor specification produced positive, nominally significant
> returns in its single 2024-2025 held-out test, including after modelled
> transaction costs: gross Sharpe 1.52 (HAC t 2.76), net Sharpe at 10 bp 1.22,
> realised market beta -0.065.

It does **not** establish durable or deployable alpha. The sealed test covers
two years only, and the cost model omits borrow cost, market impact, short
availability and capacity. Weeks 2-5 found essentially nothing distinguishable
from zero -- one specification then survived a fair test once. That is the
honest summary of the whole project, and the point of building it this way.

### Headline findings along the way

- Of the six signals, only `rvol_20` survives a Bonferroni correction on its
  information coefficient; no single factor is tradable after realistic costs.
- Fitted OLS, Ridge and gradient-boosting models never beat an equal-weighted
  composite of the six pre-registered signs, and every Week 3-4 book sits
  within about one standard error of zero.
- Risk neutralisation (sector, beta, size) fails its pre-declared test in 7 of
  8 books: it halves annualised volatility while trading costs stay flat, so a
  fixed dollar cost doubles its bite on net Sharpe. The one book that passes
  both legs is the decile-weighted composite -- neutralising it *improves* net
  Sharpe at 10 bp from 0.155 (raw) to 0.209, while cutting beta from -0.266 to
  -0.057. Every other book, including the raw composite itself, fails.
- The final specification was locked by a rule declared before any Week 5
  result existed, applied mechanically to a 40-book candidate grid (20 of
  which pass the beta constraint). The winner is the maximum of correlated
  estimates, not a significance pick -- the runner-up has a higher in-sample
  HAC t.

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
   runner's own content at that commit doesn't match what's executing, or
   `src/` has uncommitted changes on the sealed path.
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

### Pipeline stages, in order

Each stage reads only what an earlier stage wrote; run them in this order:

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
python src/evaluation/week5_lock.py

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
- `build_research_panel.py` applies the locked point-in-time investability
  screen and writes the eligible-universe/20-trading-day-target panel to
  `data/processed/research_panel/`.
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
verify the final-test machinery is correct without touching the seal.

Running the module with any other argument (including no argument) exits
immediately with a usage message, before any date is chosen -- there is no
accidental path into the sealed period.

### Tests

```powershell
python -m pytest -q
```

71 tests, a few seconds. They run against synthetic frames and do not need any
built panel, so this works even without the raw data present.

## Where to read the results

- `reports/week6_final_memo.md` -- the final word: the sealed result, its
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
