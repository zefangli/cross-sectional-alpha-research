# Research Protocol — Project 1

**Status:** locked before feature engineering and final-test inspection  
**Last updated:** 2026-08-25

## Research question

Can six interpretable price/volume signals forecast 20-trading-day
cross-sectional U.S. equity returns out of sample, and does any information
survive turnover and transaction costs?

## Data and sample

- **Source:** WRDS CRSP daily security and market-index export, documented in
  `data_manifest.md`.
- **Research sample:** 2005-01-01 through 2025-12-31.
- **Untouched final test:** 2024-01-01 through 2025-12-31. It will not be used
  for feature selection, hyperparameter selection, or model selection.
- **Initial universe:** point-in-time U.S. common equity listed on
  NYSE, AMEX, or Nasdaq, using only classifications valid on the row date,
  followed by price, liquidity, and trailing-history screens.
- **Security classification rule:** retain only `IssuerType = CORP`,
  `ConditionalType = RW`, and `TradingStatusFlg = A`; audit the excluded
  values in `data/processed/security_filter_audit.csv`. Do not use
  `SecurityActiveFlg` as a filter because it risks survivorship bias.

## Target and timing

- **Target:** 20-trading-day forward total return.
- All features at date *t* use only observations available at or before *t*.
- The cleaner produces only the validated daily panel; target construction is
  a later, separately tested step.
- **Delistings:** the target compounds the exported `DlyRet` values from
  *t*+1 through *t*+20 only when all 20 returns are present. The current
  export has no non-`N` `DlyDelFlg` values and no separate delisting-return
  field, so it cannot establish that final observed returns include delisting
  outcomes. Targets without 20 observed returns are left missing rather than
  assuming a zero post-exit return.

## Planned signals

1. Medium-term momentum, excluding the most recent 20 trading days.
2. Five-day short-term reversal.
3. Twenty-day realized volatility.
4. Volume/turnover surprise.
5. Residual (market-model) momentum.
6. Rolling drawdown.

Feature windows, transformations, and any later deviations must be recorded
in `experiments.csv` before final-test evaluation.

## Models and validation

- OLS is a sanity-check baseline only.
- Ridge regression is the primary linear benchmark.
- Gradient-boosted trees (GBM) are the nonlinear comparison.
- Use chronological expanding or rolling walk-forward validation; never random
  cross-validation.

## Portfolio and evaluation

- Begin with rank/proportional long-short weights and position caps.
- Evaluate Pearson IC, Spearman rank IC, coverage, turnover, gross/net return,
  Sharpe, drawdown, and cost sensitivity.
- Evaluate each result at **1, 5, 10, and 20 bps** per unit of turnover. The
  exact turnover convention will be stated with portfolio results.

## Eligibility and data checks

- Rows must satisfy `SecInfoStartDt <= DlyCalDt <= SecInfoEndDt`.
- Preserve delisting flag information for later delisting-return treatment.
- Before features, audit missing returns, zero volume, duplicate
  `PERMNO`/date rows, classifications, and delisting-flag behavior.

## Experiment governance

Every meaningful model, signal, or preprocessing change is logged in
`experiments.csv` with its motivation, validation period, result, and
decision. New experiments must state a hypothesis and use only the training
and validation periods until the design is frozen for the final test.
