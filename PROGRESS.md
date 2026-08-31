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

- All six locked signals implemented and evaluated through the same harness:
  `mom_120_20`, `rev_5`, `rvol_20`, `vs_20`, `rmom_120_20`, `dd_252`. Residual
  momentum fits one SQL expression because the sum of market-model residuals
  has a closed form in window aggregates; a test checks it against an explicit
  numpy OLS fit.
- Verified that `price`, `volume` and `shares_outstanding` are as-traded in this
  export while `ret` is split-adjusted (checked on Apple's 2014 7:1 split), so
  volume surprise uses turnover and drawdown uses a cumulative return index.
  Both have split-invariance tests.
- Portfolio statistics are now averaged over all 20 rebalance offsets. A single
  offset gave `rev_5` a negative gross Sharpe despite a significantly positive
  IC; the offset spread runs -0.315 to +0.547 for that factor.
- Maximum drawdown now floors the running peak at starting wealth 1.0.
- Week 2 result: `rvol_20` and `vs_20` survive Bonferroni across the six tests;
  `rev_5` does not; `dd_252` is insignificant; `mom_120_20` is a null and
  `rmom_120_20` is a null with the wrong sign. No factor is viable at 20 bp and
  only `mom_120_20` and `rvol_20` are positive at 10 bp. Five of six show
  hump-shaped decile returns, so tail-decile books understate the signals.
- Logged as W2-002 .. W2-007 and written up in `reports/factor_memo_week2.md`;
  the portfolio numbers in `reports/factor_memo_01_momentum.md` are superseded.
- 20 tests pass, including a shared leakage test that perturbs every input on
  every row after t and asserts all six factors are unchanged at t.

## Next

- Week 3: walk-forward splitting and portfolio infrastructure. Two Week 2
  findings should shape it: use rank-based continuous weights rather than
  tail-decile books, and report portfolio statistics averaged over rebalance
  offsets with the spread.
- Check whether `rvol_20`, `dd_252`, `mom_120_20` and `rmom_120_20` are four
  signals or one before combining them; their bottom deciles look like the same
  distressed, high-volatility names.
