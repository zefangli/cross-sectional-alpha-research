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
- Week 2 result: only `rvol_20` survives Bonferroni across the six tests;
  `vs_20` and `rev_5` do not; `dd_252` is insignificant; `mom_120_20` is a null and
  `rmom_120_20` is a null with the wrong sign. No factor is viable at 20 bp and
  only `mom_120_20` and `rvol_20` are positive at 10 bp. Five of six show
  hump-shaped decile returns, so tail-decile books understate the signals.
- Timing corrected (W2-008): `vs_20` and `dd_252` originally used day-t inputs,
  which is leakage-free against a t+1 target but implies same-close execution.
  Both are now lagged to t-1, so all six factors are determined by the close of
  t-1 and the shared leakage test perturbs row t itself. This cost `vs_20` about
  a third of its IC (NW t 3.43 -> 2.50); `rvol_20` is now the only factor that
  survives Bonferroni across the six tests.
- Logged as W2-002 .. W2-008 and written up in `reports/factor_memo_week2.md`;
  the portfolio numbers in `reports/factor_memo_01_momentum.md` are superseded.
- 20 tests pass, including a shared leakage test that perturbs every input on
  every row after t and asserts all six factors are unchanged at t.

## Week 3

- Aligned six-factor rank panel materialised at `data/processed/factor_panel/`:
  8,319,133 rows, 99.05% of eligible, mean 1,660 names per date.
- Cross-factor structure measured (W3-001). The Week 2 suspicion is confirmed:
  `rmom_120_20` and `mom_120_20` correlate 0.73 by rank and 0.76 by portfolio
  return; `rvol_20` and `dd_252` books correlate 0.87. Only `rev_5` and `vs_20`
  are independent. Portfolio-return correlation is the informative measure --
  `mom_120_20` and `rvol_20` look independent by rank (-0.10) yet their books
  correlate 0.46.
- Ten fixed expanding walk-forward folds with a 20-trading-day purge before each
  validation year, so no fold trains on returns realised inside its validation
  window (W3-002). Final fold stops at 2023-11-30.
- Baseline portfolio built: dollar-neutral, 1% position cap, rank-continuous
  weights, 20 staggered daily cohorts, daily-marked P&L, turnover, costs and
  exposures (W3-003). Composite gross Sharpe 0.121, breakeven 8.7 bp, nothing
  clears 10 bp. The position cap never binds at this universe size.
- Dollar-neutral is not beta-neutral: `rvol_20` carries beta -0.34, `dd_252`
  -0.28, the composite -0.23, negative in every rolling 252-day window.
- Weighting ablation (W3-004) rejected the Week 2 claim that rank-continuous
  weights would improve on tail deciles: decile weighting wins 5 of 7 on gross
  Sharpe and 6 of 7 on turnover. Rank weighting is kept as the pre-declared
  Week 4 baseline regardless, and both are carried forward.
- 32 tests pass.

## Week 4

- Walk-forward model layer built (`src/models/walk_forward.py`): OLS, Ridge and
  gradient boosting fitted independently inside each of the ten Week 3 folds,
  over the six factor ranks. Gradient boosting is sklearn's
  `HistGradientBoostingRegressor`; LightGBM was not installed and was not added
  for one model.
- 12,879,195 validation-only predictions written (4,293,065 per model), dated
  2014-01-02 to 2023-11-30, with no warm-up rows. The books get their single
  ramp from one continuous 2014-2023 backtest rather than a per-fold warm-up;
  see W4-005 below for why the warm-up was withdrawn. Preprocessing is inside an
  sklearn Pipeline and the ridge alpha search runs on a purged inner
  chronological split of the training dates only.
- Windows to keep distinct: fitting, prediction and cohort formation all stop on
  2023-11-30; portfolio P&L is marked through 2023-12-29 to run off the cohorts
  formed up to that date. No 2024 or 2025 observation is read either way.
- No point-prediction skill (W4-001): out-of-sample R2 is negative for all three
  models against the training-period mean. The edge is entirely in ordering --
  rank IC 0.0220 for OLS (NW t 8.82), 0.0197 for GBM (t 7.74).
- No model beats the pre-registered composite (W4-002, recomputed under W4-005).
  Composite gross Sharpe 0.297 and breakeven 22.2 bp; best model book
  `gbm__decile` 0.099 and 5.9 bp. Only the two composite books are net-positive
  at 10 bp; every model book is negative there. The models trade more for less:
  OLS earns 0.45% gross on a 0.70 book at 6.8x annual turnover against the
  composite's 2.50% on a 0.90 book at 5.6x.
- The Week 3 bar was stale (W4-003). Recomputing the composite on the same
  2014-2023 validation dates moves it from 0.121 to 0.297 gross Sharpe and from
  8.7 bp to 22.2 bp breakeven; the recomputation matches the Week 3 daily series
  exactly outside the ramp days, so it is a window effect, not a code change.
- Warm-up contamination found and corrected (W4-005). The first version
  pre-ramped each fold's book on the 20 trading days before its validation year,
  which is exactly the window in which the training rows' 20-day targets are
  realised, so those cohorts traded on look-ahead. Predictions and cohorts are
  now validation-only and the ten folds run as one continuous backtest with
  cohorts carrying across annual model changes. Model books fell 31-43% of gross
  Sharpe, the composite 11% -- the asymmetry the mechanism predicts, since the
  composite depends on no fitted model. This also fixed an unintended per-fold
  cohort reset that truncated year-end tail P&L. Prediction IC and R2 are
  unaffected.
- Portfolio inference is now Newey-West HAC at 20 lags (W4-006), since the
  staggered cohorts induce serial dependence. The correction is mild, within
  0.07 of the naive statistic everywhere.
- Nothing in the study is statistically distinguishable from zero. Every book
  has a HAC |t| <= 1.01 on its gross Sharpe over ten years, the models sit at
  0.26-0.32, and the 2006-2013 versus 2014-2023 difference has t = 0.85. Week 4
  compared a null against three other nulls; the composite lost least.
- Ridge alpha is unidentified under MSE selection (W4-004): the inner search
  returned the grid maximum in all ten folds, MSE keeps falling out to alpha
  1e10 for a 0.005% total gain, yet predictions at 1e4 and 1e10 correlate only
  0.86 by daily cross-sectional rank because ridge rotates coefficients rather
  than scaling them. MSE is the wrong criterion for a ranking problem. The
  pre-registered grid is kept and Ridge is not retuned; rank-IC selection moves
  to Week 5 as a separate, declared, training-only robustness experiment.
- The models independently learned a negative loading on `mom_120_20`, against
  its pre-registered sign, matching Week 2's direct finding.
- Written up in `reports/week4_model_memo.md`. 40 tests pass, including a
  named regression test for the warm-up bug.

## Week 5

- CRSP `SICCD` audited and confirmed point-in-time (W5-001): it rides on the
  SecInfo interval records and 12,079 of 21,548 PERMNOs carry more than one code
  over time. Two traps avoided -- the `SecurityHdrFlg='Y'` row matches the first
  interval more often than the last (7,420 against 3,137) so it is never used,
  and 9.8% of interval rows carry sentinel codes clustering on delisting stubs,
  for which the prior interval is carried forward and a later one never is.
- Point-in-time exposures built (W5-002): sector, `beta_252` and `log_mcap`, all
  determined at the close of t-1, 100% coverage on the aligned panel. Complete
  coverage is structural, since Week 1 eligibility already requires the 252
  prior returns the beta window needs.
- Neutralisation FAILS its pre-declared test in 7 of 8 books (W5-003). Every
  book sheds 75-98% of realised market beta, so that leg passes everywhere; net
  Sharpe at 10 bp gets worse, so the second leg fails. Only `composite__decile`
  passes both.
- The mechanism is the week's most useful finding: neutralisation halves
  annualised volatility (8.43% to 4.12%) while turnover and dollar cost drag
  stay flat (5.64x to 5.72x, 1.13% to 1.14%). A fixed trading cost charged
  against half the risk budget doubles its bite in Sharpe terms. It cannot be
  levered away, since net Sharpe is leverage-invariant. On gross Sharpe alone
  `ols` and `ridge` nearly tripled and this would have been recorded as a win.
- Ablation (W5-004): `rmom_120_20` and `vs_20` are redundant by the pre-declared
  rule, `mom_120_20` and `rev_5` are not, `rvol_20`/`dd_252` are inconclusive.
  Every ablated book sits at HAC |t| 0.81-1.29, so nothing is dropped.
- Robustness (W5-005): the low-volatility tercile (HAC t 2.43) and calendar 2018
  (2.21) are best-of-many ex-post slices of a series whose full-sample t is 1.0,
  and the tercile boundaries are full-sample quantiles, so that split is not
  even implementable. Neither is treated as a finding. Across pre-declared
  horizons {5,10,20,40} gross Sharpe moves only 0.297-0.383 while breakeven
  swings 10.4 to 38.5 bp -- the project's headline breakeven is fragile to an
  arbitrary holding-period choice.
- The first candidate grid was incomplete and the lock has been corrected
  (W5-007). The rule varies weighting, neutralisation and factor set, but only
  raw ablations were ever evaluated, and since every raw ablation fails the beta
  constraint, factor set could not compete. All 12 neutralised ablations pass
  it. The grid went from 28 candidates with 8 admissible to 40 with 20, and the
  winner changed.
- Final specification locked by the unchanged W5-006 rule, applied
  programmatically by `src/evaluation/week5_lock.py` to
  `reports/week5/candidates.csv`: **`drop_rmom_120_20__neutral__decile`** --
  the five-factor composite dropping `rmom_120_20`, neutralised, decile
  weighted. Realised beta -0.056, gross Sharpe 0.534 (HAC t 1.65), net Sharpe at
  10 bp +0.238. The dropped factor is the one W5-004R had already flagged as the
  redundant half of the momentum pair.
- The lock is a procedural commitment, not a claim of edge, and three things cut
  against it: completing the grid made the selection statistically weaker, since
  the winner is now the max of 20 correlated admissible estimates rather than 8;
  the margin over the runner-up is 0.0103 with the top four books spanning
  0.209-0.238; and the runner-up has the higher HAC t (1.97 against 1.65),
  because the rule selects on net Sharpe, not significance, as pre-registered.
  HAC t 1.65 is about p = 0.10 and is still not significant.
- The Week 6 protocol is executable and frozen (W5-008). `week6_final.py` reads
  the lock at runtime, hardcodes no book, and refuses on a missing field, a
  factor sign disagreeing with `FACTOR_SIGN`, a recorded commit that is not an
  ancestor of HEAD, or an uncommitted `src/` on the sealed path. Reaching the
  sealed period requires the literal string
  `run-sealed-2024-2025-exactly-once`; no argument exits before any data is
  opened. Its `replay` mode reproduces the locked book's Week 5 figures to about
  1e-15.
- Four blocking defects found in review and fixed before the sealed run
  (W5-010). The worst was a P0: the sealed formation start inherited
  `walk_forward_splits`' default first validation year of 2014, so the one-shot
  final test would have evaluated 2014-2025 and reported ten selection-sample
  years as the held-out result. It is now read off the panel as the first trading date on
  or after 2024-01-01 and asserted. The cohort cutoff was a hardcoded Sunday
  resolving two cohorts early and is now derived as `pnl_end_tdi - hold_days`
  (2025-12-02). Exactly-once is enforced by an atomic `O_CREAT|O_EXCL` marker
  rather than by the opt-in token alone. Provenance now covers the lock JSON and
  requires the runner's content at the recorded commit to be byte-identical to
  the executing file. Replay is unchanged and still reproduces all five recorded
  figures, so the validation baseline was not perturbed.
- Specification relocked against the corrected runner (W5-011). Regeneration is
  deterministic -- same winner, same figures, 40 candidates with 20 admissible --
  with the recorded commit moved to the one containing the corrected runner. All
  three provenance guards now pass. No final artifact or run marker exists.
- **The sealed period is outcome-sealed but was not literally untouched**
  (W5-009). Exposures are built over full panel history because a t-1 rolling
  beta needs it, and the first exposure audit summarised coverage and sector
  counts over 2024-2025 covariate rows. No return, target or performance figure
  from the sealed period was ever computed. The winsorisation quantiles came
  from a beta range measured on a query restricted to dates through 2023-11-30.
  The audit now ends at 2023-11-30, and this is disclosed rather than described
  as an untouched seal.
- Written up in `reports/week5_neutralisation_memo.md`. 71 tests pass.

## Week 6 -- the sealed final test

- The sealed period was opened exactly once, on 2026-09-11, at commit `084f5eb`,
  running the specification locked at `fbbe574` unchanged. An atomic
  `sealed_run_started.json` marker records the run and prevents repetition.
- Formation 2024-01-02 to 2025-12-02, P&L 2024-01-03 to 2025-12-31, 501 trading
  days, rank IC on the 482 formation dates.
- **Result (W6-001): gross Sharpe 1.522 with a HAC t of 2.76; net Sharpe 1.491,
  1.368, 1.215 and 0.909 at 1, 5, 10 and 20 bp; breakeven 49.7 bp; realised
  market beta -0.065; max drawdown -4.1%; annual turnover 8.86x; mean rank IC
  0.0364 with a HAC t of 4.63.** Profitable at every cost tier tested, and beta
  stayed inside the selection rule's 0.10 constraint out of sample, which it had
  no obligation to do.
- The result is NOT significantly better than the selection-sample estimate
  (W6-002). Out-of-sample 1.522 against selection-sample 0.534 is a difference
  of +0.99; computed with HAC-consistent standard errors the difference has a
  standard error of 0.639, so t is about 1.55 -- not significant. The primary
  HAC 95% interval on the out-of-sample Sharpe is [0.44, 2.60]: the mean return
  is distinguishable from zero, while its magnitude is loosely pinned down.
- Both calendar years are positive (2024 Sharpe 1.39, HAC t 1.73; 2025 Sharpe
  1.65, HAC t 2.22), recorded descriptively with neither preferred. Two adjacent
  years of one market are consistency, not two experiments.
- The dropped factor is still an exposure: mean `rmom_120_20` exposure is 0.248
  despite its exclusion, because the five retained factors correlate with it.
  The largest exposures remain `mom_120_20` (0.443) and `dd_252` (0.355) -- the
  Week 3 cluster, never fully defused.
- Written up in `reports/week6_final_memo.md`. 71 tests pass.

## Next

- Nothing. The specification is locked, the sealed period is spent, and this
  test is not repeatable on this data.
- The honest summary of the project: Weeks 2 through 5 found essentially nothing
  distinguishable from zero, and one pre-registered specification then survived a
  fair two-year out-of-sample test. That is a weak signal that passed a real
  test once, not an established edge.
- What would change the conclusion is more out-of-sample time, not more analysis
  of 2024-2025. Any further work on this dataset is in-sample by construction and
  must be labelled as such.
