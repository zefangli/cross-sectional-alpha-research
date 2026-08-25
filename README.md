# Cross-Sectional Equity Alpha Research

An auditable, point-in-time CRSP research pipeline for testing whether six
interpretable price/volume signals forecast 20-trading-day cross-sectional
returns after turnover and transaction costs.

## Status

Week 0 design is locked. Week 1 begins with the cleaned return panel; no
features or targets are produced by the cleaner.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/data/clean_crsp.py
```

The raw export is deliberately excluded from Git. Place it at
`crsp/yb8xejbnpiflaprb.csv` (the current local path) and do not edit it.

The command writes a year-partitioned daily panel under
`data/processed/crsp_daily_panel/` plus a validation summary at
`data/processed/cleaning_validation.csv`.

## Project layout

```text
config/       locked parameters as work starts
data/         local generated data only (not versioned)
src/data/     ingestion and validation
tests/        small checks for critical transformations
reports/      research memos and final report
notebooks/    exploratory analysis only
```

The protocol and experiment log are the source of truth for research choices.
