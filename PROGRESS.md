# Implementation Progress

## Completed

- Week 0 research design locked in `research_protocol.md`.
- Raw CRSP export is immutable, checksummed, and ignored by Git.
- Streaming CSV-to-Parquet cleaner built and verified.
- Cleaned panel covers 2005-01-03 through 2025-12-31 with zero
  classification-date violations and zero exact duplicate `PERMNO`/date rows.
- Security filter locked to point-in-time corporate, regular-way, active
  common equities; `SecurityActiveFlg` is not used. Exchange, issuer,
  conditional-type and trading-status screens are entry eligibility, not row
  filters: the cleaner keeps every common-share row plus each such security's
  delisting event row (`DlyDelFlg = 'Y'`, placeholder classifications), so a
  held name keeps being marked after a status change and is paid its
  delisting return. One event row is kept per delisted PERMNO, deduplicated,
  with identity rows winning ties; such a row is never a formation row.

- Point-in-time eligible universe and 20-trading-day forward total-return
  target built from the processed Parquet panel only, with eligibility
  decided at the close of t-1.
- Eligibility requires price >= $5, 20 prior daily dollar-volume observations
  averaging >= $5m, and at least 252 prior valid returns.
- Research-panel checks: 22,324,891 rows; 8,395,800 eligible rows; 8,319,866
  eligible rows with complete targets; all behavioral tests pass.
- `forward_return_20d_observed` compounds whatever was actually observed
  over the 20 days, delisting return included, and is what the book is marked
  on; the complete label (`forward_return_20d`) remains the requirement for
  IC and model targets. Names with no observation at all are rare (about
  0.006 per date).

- Week 2 vertical slice: reusable single-factor evaluation harness
  (`src/features/factors.py`, `src/evaluation/factor_eval.py`) plus the first
  factor, medium-term momentum `mom_120_20`.
- Evaluation is sealed at the target window, not the observation date: the last
  evaluated date is 2023-11-30, so no 2024 return enters any statistic.
- Portfolio formation uses every eligible stock with a signal; IC is a
  separate complete-pair diagnostic (target coverage 99.5%), so formation
  never conditions on a stock's future target being observable.
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
- Portfolio statistics are averaged over all 20 rebalance offsets. A single
  offset gave `rev_5` a negative gross Sharpe despite a significantly positive
  IC; the offset spread runs -0.315 to +0.547 for that factor.
- Maximum drawdown floors the running peak at starting wealth 1.0.
- All six factors are determined by the close of t-1 (`vs_20` and `dd_252`
  lag one day like the rest), and the shared leakage test perturbs every
  input on every row after t and asserts all six factors are unchanged at t.
- Week 2 result: `rvol_20` (NW t -2.85) and `vs_20` (2.73) survive Bonferroni
  across the six tests; `rev_5` does not; `dd_252` is insignificant;
  `mom_120_20` is a null and `rmom_120_20` is a null with the wrong sign. No
  factor is viable at 20 bp and only `mom_120_20` and `rvol_20` are positive
  at 10 bp. Five of six show hump-shaped decile returns, so tail-decile books
  understate the signals.
- Logged as W2-002 .. W2-008 and written up in `reports/factor_memo_week2.md`.
- 20 tests pass, including a shared leakage test that perturbs every input on
  every row after t and asserts all six factors are unchanged at t.

## Week 3

- Aligned six-factor rank panel materialised at `data/processed/factor_panel/`:
  8,319,133 rows, 99.05% of eligible, mean 1,660 names per date.
- Cross-factor structure measured (W3-001). `rmom_120_20` and `mom_120_20`
  correlate 0.73 by rank and 0.76 by portfolio return; `rvol_20` and `dd_252`
  books correlate 0.87. Only `rev_5` and `vs_20` are independent.
  Portfolio-return correlation is the informative measure -- `mom_120_20` and
  `rvol_20` look independent by rank (-0.10) yet their books correlate 0.46.
- Ten fixed expanding walk-forward folds with a 20-trading-day purge before each
  validation year, so no fold trains on returns realised inside its validation
  window (W3-002). Final fold stops at 2023-11-30.
- Baseline portfolio built: dollar-neutral, 1% position cap, rank-continuous
  weights, 20 staggered daily cohorts, daily-marked P&L, turnover, costs and
  exposures (W3-003). Trading is charged against holdings drifted by the
  previous day's returns over the grown NAV, not against yesterday's target
  weights -- restoring a target after a price move is itself a trade. A name
  that delists is settled to cash the day after its event row: a single
  correctly-sized exit trade takes the drifted post-event value to zero, with
  no equity exposure or repurchase attempt afterward. An unknown (NULL) event
  return already accrues zero under the missing-return policy, so its
  settlement exit is a disclosed zero-return assumption, measured separately
  as `gross_unknown_event_payoff` rather than folded into ordinary
  settlement. The execution-timing diagnostic, `traded_missing_execution_return`,
  checks whether CRSP recorded a return on the trade's true execution date
  (the close of d-1, except a terminal-liquidation trade, which executes at
  its own close) -- it is a return-availability proxy, not a check on price,
  trading status or settlement type.
- Composite gross Sharpe 0.121, breakeven 8.7 bp on the Week 3 validation
  dates, nothing clears 10 bp. The position cap never binds at this universe
  size. (Week 4 recomputes this bar on the full 2014-2023 window; see below.)
- Dollar-neutral is not beta-neutral: `rvol_20` carries beta -0.34, `dd_252`
  -0.28, the composite -0.23, negative in every rolling 252-day window.
- Weighting ablation (W3-004): decile weighting wins 6 of 7 on gross Sharpe
  and 6 of 7 on turnover, against the expectation that rank-continuous
  weights would improve on tail deciles -- rank weights don't avoid the
  broken tail buckets, they add the low-signal middle and its trading.
  Decile weighting is kept as the pre-declared Week 4 baseline, and both are
  carried forward.
- 32 tests pass.

## Week 4

- Walk-forward model layer built (`src/models/walk_forward.py`): OLS, Ridge and
  gradient boosting fitted independently inside each of the ten Week 3 folds,
  over the six factor ranks. Gradient boosting is sklearn's
  `HistGradientBoostingRegressor`; LightGBM was not installed and was not added
  for one model.
- 12,879,195 validation-only predictions written (4,293,065 per model), dated
  2014-01-02 to 2023-11-30, with no warm-up rows. The books get their single
  ramp from one continuous 2014-2023 backtest rather than a per-fold warm-up
  (see W4-005 below). Preprocessing is inside an sklearn Pipeline and the
  ridge alpha search runs on a purged inner chronological split of the
  training dates only.
- Windows to keep distinct: fitting, prediction and cohort formation all stop on
  2023-11-30; portfolio P&L is marked through 2023-12-29 to run off the cohorts
  formed up to that date. No 2024 or 2025 observation is read either way.
- No point-prediction skill (W4-001): out-of-sample R2 is negative for all three
  models against the training-period mean (GBM +0.0003, OLS/Ridge -0.0002).
  The edge is entirely in ordering -- mean rank IC about 0.022, with a
  Newey-West t (on the daily IC series sorted by date before the HAC
  statistic) of about 2.0 for OLS/Ridge and 2.3 for GBM.
- No model beats the pre-registered composite (W4-002, recomputed under W4-005).
  Composite gross Sharpe 0.281, net +0.125 at 10 bp; best model book
  `gbm__decile` 0.294 gross, -0.042 net -- the model edges the composite on
  gross Sharpe (both HAC t about 1.0) and still loses net of costs. The
  models trade more for less: OLS earns 0.09% gross on a 0.83 book at 6.5x
  annual turnover against the composite's 2.32% on a 0.90 book at 6.4x.
- The Week 3 bar was stale (W4-003). Recomputing the composite on the same
  2014-2023 validation dates moves it from 0.121 to 0.281 gross Sharpe and
  from 8.7 bp to about 22 bp breakeven; the recomputation matches the Week 3
  daily series exactly outside the ramp days, so it is a window effect, not a
  code change.
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
- Portfolio inference is Newey-West HAC at 20 lags (W4-006), since the
  staggered cohorts induce serial dependence; the daily IC series is sorted by
  date before the statistic is computed.
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
  annualised volatility (8.28% to 4.12%) while turnover and dollar cost drag
  stay flat (6.41x to 6.43x). A fixed trading cost charged against half the
  risk budget cuts net Sharpe at 10 bp from 0.126 to 0.029 -- to under a
  quarter, not half, because neutralisation strips edge as well as beta. It
  cannot be
  levered away, since net Sharpe is leverage-invariant. On gross Sharpe alone
  `ols` and `ridge` nearly tripled, which alone would read as a win.
- Ablation (W5-004): `rmom_120_20` and `vs_20` are redundant by the pre-declared
  rule, `mom_120_20` and `rev_5` are not, `rvol_20`/`dd_252` are inconclusive.
  Every ablated book sits at HAC |t| 0.81-1.29, so nothing is dropped.
- Robustness (W5-005): the low-volatility tercile (HAC t 2.42) and calendar 2018
  (2.33) are best-of-many ex-post slices of a series whose full-sample t is
  0.96, and the tercile boundaries are full-sample quantiles, so that split is
  not even implementable. Neither is treated as a finding. Across pre-declared
  horizons {5,10,20,40} gross Sharpe moves only 0.286-0.359 (every HAC t in
  0.96-1.19) while breakeven swings 8.0 to 27.2 bp -- the project's headline
  breakeven is fragile to an arbitrary holding-period choice.
- The candidate grid varies weighting, neutralisation and factor set (W5-007).
  Since every raw ablation fails the beta constraint, factor set could not
  compete on raw books; all 12 neutralised ablations pass it. The grid runs
  40 candidates with 20 admissible.
- Final specification locked by the pre-declared W5-006 rule, applied
  programmatically by `src/evaluation/week5_lock.py` to
  `reports/week5/candidates.csv`: **`drop_rmom_120_20__neutral__decile`** --
  the five-factor composite dropping `rmom_120_20`, neutralised, decile
  weighted. Realised beta -0.057, gross Sharpe 0.493 (HAC t 1.53), net Sharpe at
  10 bp +0.136, breakeven 13.8 bp. The dropped factor is the one W5-004 had
  already flagged as the redundant half of the momentum pair.
- The lock is a procedural commitment, not a claim of edge, and three things cut
  against it: the winner is the max of 20 correlated admissible estimates, not
  a significance pick; the margin over the runner-up is narrow, well inside the
  noise of a single Sharpe estimate; and more than one admissible candidate
  carries a higher selection-sample HAC t than the winner, because the rule
  selects on net Sharpe, not significance, as pre-registered. The winner's own
  HAC t 1.53 is not significant.
- On the corrected selection sample the same rule would pick a different book:
  `drop_vs_20__neutral__decile` at net Sharpe 0.157 against the locked book's
  0.136. The lock is kept -- re-selecting after the sealed period was opened
  would turn a pre-registered test into a fitted one -- but the flip is
  disclosed, and is itself evidence of how little separated the candidates
  (0.02 apart, on HAC t of 1.44 and 1.53).
- The Week 6 protocol is executable and frozen (W5-008). `week6_final.py` reads
  the lock at runtime, hardcodes no book, and refuses on a missing field, a
  factor sign disagreeing with `FACTOR_SIGN`, a recorded commit that is not an
  ancestor of HEAD, or an uncommitted `src/` on the sealed path. Reaching the
  sealed period requires the literal string
  `run-sealed-2024-2025-exactly-once`; no argument exits before any data is
  opened. Exactly-once is enforced by an atomic `O_CREAT|O_EXCL` marker rather
  than by the opt-in token alone. Its `replay` mode reproduces the locked
  book's Week 5 figures to about 1e-15. The lock file is immutable by default:
  rerunning `week5_lock.py` writes to `reports/week5/reselection.json` unless
  `--relock` is passed.
- The sealed period is outcome-sealed but not literally untouched (W5-009).
  Exposures are built over full panel history because a t-1 rolling beta needs
  it, so 2024-2025 covariate rows (sector, beta, size) are read to build
  exposures and to set winsorisation quantiles, and this is disclosed in
  `reports/week5_neutralisation_memo.md`, section 11. No return, target or
  performance figure from the sealed period was ever computed before Week 6.
- Written up in `reports/week5_neutralisation_memo.md`. 71 tests pass.

## Week 6 -- the sealed final test

- The sealed period was opened exactly once, on 2026-09-11, at commit `084f5eb`,
  running the specification locked at `fbbe574` unchanged. An atomic
  `sealed_run_started.json` marker records the run and prevents repetition.
- Formation 2024-01-02 to 2025-12-02, P&L 2024-01-03 to 2025-12-31, 501 trading
  days, rank IC on the 482 formation dates.
- **Result: gross Sharpe 1.429 with a HAC t of 2.71; net Sharpe 1.39 / 1.24 /
  1.06 / 0.69 at 1, 5, 10 and 20 bp (net@10bp HAC t 2.01); breakeven 38.5 bp;
  realised market beta -0.063; max drawdown -3.6%; annual turnover 10.4x; mean
  rank IC 0.031 with a HAC t of 3.95.** Profitable at every cost tier tested,
  and beta stayed inside the selection rule's 0.10 constraint out of sample,
  which it had no obligation to do.
- These are a recomputation of the unchanged locked specification over the
  already-seen 2024-2025 period, not a second sealed test. The seal was opened
  once, under the pipeline as it then stood; `reports/week6/` holds that run's
  own numbers. A recomputation on seen data is weaker evidence than the
  original one-shot test.
- The result is not significantly better than the selection-sample estimate.
  Out-of-sample 1.429 against selection-sample 0.493 is a difference of +0.94;
  computed with HAC-consistent standard errors the difference has a standard
  error of 0.618, so t is about 1.51 -- not significant. The HAC 95% interval
  on the out-of-sample Sharpe is [0.40, 2.46]: the mean return is
  distinguishable from zero, while its magnitude is loosely pinned down.
- Both calendar years are positive, recorded descriptively with neither
  preferred. Two adjacent years of one market are consistency, not two
  experiments.
- The dropped factor is still an exposure: mean `rmom_120_20` exposure is 0.248
  despite its exclusion, because the five retained factors correlate with it.
  The largest exposures remain `mom_120_20` (0.443) and `dd_252` (0.355) -- the
  Week 3 cluster, never fully defused.
- Positions with no return recorded for the day, driven by delisted names
  before settlement, average 0.008 per day (gross weight 0.0007% of NAV, max
  0.20%); a real short position, PERMNO 16795, delisted 2024-10-28 with no
  recorded return, contributes 0.056% of NAV to `gross_unknown_event_payoff`
  -- a disclosed zero-return imputation on an event whose own return is
  unknown, not an observed payoff. The fraction of traded notional with no
  return recorded on its execution date is 0.002%, a return-availability
  proxy rather than a check on tradable price.
- Written up in `reports/week6_final_memo.md`. 101 tests pass.

## Next

- Nothing on this data. The specification is locked, the sealed period is
  spent, and this test is not repeatable on this data.
- Next research additions, none started: long/short attribution against
  standard risk factors, borrow and impact costs with capacity scenarios, and
  genuinely new forward evidence.
- The honest summary of the project: Weeks 2 through 5 found essentially nothing
  distinguishable from zero, and one pre-registered specification then survived a
  fair two-year out-of-sample test. That is a weak signal that passed a real
  test once, not an established edge.
- What would change the conclusion is more out-of-sample time, not more analysis
  of 2024-2025. Any further work on this dataset is in-sample by construction and
  must be labelled as such.
