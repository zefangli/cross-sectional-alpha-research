# Implementation Progress

## Completed

- Week 0 research design locked in `research_protocol.md`.
- Raw CRSP export is immutable, checksummed, and ignored by Git.
- Streaming CSV-to-Parquet cleaner built and verified.
- Cleaned panel covers 2005-01-03 through 2025-12-31 with zero
  classification-date violations and zero exact duplicate `PERMNO`/date rows.
- Security filter locked to point-in-time corporate, regular-way, active
  common equities; `SecurityActiveFlg` is not used.

- Point-in-time eligible universe and 20-trading-day forward total-return
  target built from the processed Parquet panel only.
- Eligibility requires price >= $5, 20 prior daily dollar-volume observations
  averaging >= $5m, and at least 252 prior valid returns.
- Research-panel checks: 21,104,236 rows; 8,399,139 eligible rows; 8,321,030
  eligible rows with complete targets; all behavioral tests pass.
- Delisting-return limitation documented: this export has no explicit
  delisting-return field, so incomplete post-exit target windows are censored.

- Week 2 vertical slice: reusable single-factor evaluation harness
  (`src/features/factors.py`, `src/evaluation/factor_eval.py`) plus the first
  factor, medium-term momentum `mom_120_20`.
- Evaluation is sealed at the target window, not the observation date: the last
  evaluated date is 2023-11-30, so no 2024 return enters any statistic.
- Momentum result over 2006-2023: mean rank IC -0.00002 (Newey-West t = 0.00),
  non-monotonic decile returns, ~90% turnover per 20-day rebalance, gross
  Sharpe 0.188, net Sharpe 0.088 at 10 bp and -0.011 at 20 bp, breakeven ~19 bp.
  Logged as W2-001 and written up in `reports/factor_memo_01_momentum.md`.
- Factor tests cover the known-value window, the skipped recent month, future
  perturbation, history gaps, turnover with position exits, and Newey-West.

## Next

- Apply the same harness to reversal, realised volatility, volume surprise,
  residual momentum and drawdown by adding entries to `FACTOR_SQL` /
  `FACTOR_SIGN`; nothing in the evaluation changes.
- Extend the first factor memo into the combined Week 2 factor-research memo
  once all six results exist.
