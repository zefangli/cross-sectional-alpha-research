# Cross-Sectional Equity Alpha Research

An auditable, point-in-time CRSP research pipeline for testing whether six
interpretable price/volume signals forecast 20-trading-day cross-sectional
returns after turnover and transaction costs.

## Status

Weeks 0-4 complete; see `PROGRESS.md` for the running record and `reports/` for
the memos. The panel, the six factors, the ten walk-forward folds and the
staggered-cohort portfolio engine are built and tested.

The result so far is a null. Of the six signals only `rvol_20` survives a
Bonferroni correction on its information coefficient, and no signal is tradable
after realistic costs. OLS, Ridge and gradient boosting fitted over the ten
folds all fail to beat an equal-weighted composite of the six pre-registered
signs, and every book in the study -- models and baseline alike -- has a gross
Sharpe within about one standard error of zero. This is reported as it stands
rather than searched away.

Weeks 5-6 remain: risk neutralisation, then a single pass over the sealed
2024-2025 final test. No 2024 or 2025 observation has been evaluated.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/data/clean_crsp.py
python src/data/build_research_panel.py
python src/features/build_factor_panel.py
python src/evaluation/factor_eval.py
python src/evaluation/week3_baseline.py
python src/models/walk_forward.py
python src/evaluation/week4_models.py
```

The stages run in order and each reads only what the one before it wrote.

The raw export is deliberately excluded from Git. Place it at
`crsp/yb8xejbnpiflaprb.csv` (the current local path) and do not edit it.

The command writes a year-partitioned daily panel under
`data/processed/crsp_daily_panel/` plus a validation summary at
`data/processed/cleaning_validation.csv`.

The second command applies the locked point-in-time investability screen and
writes the eligible-universe/20-trading-day-target panel to
`data/processed/research_panel/`, with its audit in
`data/processed/research_panel_validation.csv`.

The remaining stages build the aligned six-factor rank panel, evaluate each
factor on its own, build the Week 3 baseline portfolio, fit the walk-forward
models, and score them. Their outputs land under `reports/`. Nothing in the
pipeline reads a date after 2023-11-30; the 2024-2025 final test is opened once,
in Week 6.

Run the checks with `python -m pytest -q` (39 tests, a few seconds; they use
synthetic frames and do not need the built panel).

## Project layout

```text
config/          locked parameters as work starts
data/            local generated data only (not versioned)
src/data/        ingestion and validation
src/features/    factor definitions and the aligned rank panel
src/models/      walk-forward splits and model fitting
src/portfolio/   the staggered-cohort backtest engine
src/evaluation/  factor, baseline and model evaluation drivers
tests/           small checks for critical transformations
reports/         research memos and final report
notebooks/       exploratory analysis only
```

The protocol and experiment log are the source of truth for research choices.
