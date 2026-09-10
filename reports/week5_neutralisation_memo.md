# Week 5: Risk neutralisation, robustness, and the locked specification

Date: 2026-09-10. Experiments: W5-001 .. W5-006.
Formation 2014-01-02 to 2023-11-30; P&L to 2023-12-29. 2024-2025 sealed.

Specifications W5-001 to W5-006, including the W5-003 success criterion and the
W5-006 selection rule, were written into `experiments.csv` before any Week 5
result existed. Results are appended as separate rows rather than overwriting
the declarations, so both remain in the log. The protection is procedural --
declared before the numbers were seen -- not cryptographic: the declaration and
the results were committed in the same session.

## 1. Is CRSP's SIC field point-in-time? (W5-001)

Yes, and the audit mattered, because two of its findings would have produced
silent look-ahead.

`SICCD` rides on the `SecInfoStartDt`/`SecInfoEndDt` interval records, the same
mechanism Week 1 locked for the universe screen. It is genuinely time-varying:
12,079 of 21,548 PERMNOs carry more than one code, and PERMNO 10001 moves
4920 to 4925 on 2009-12-18. A backfilled header field would show exactly one
code per PERMNO.

Two traps, both avoided:

- **The header row is not the current value.** For PERMNOs whose code changed,
  `SecurityHdrFlg = 'Y'` matches the *first* interval more often (7,420) than
  the last (3,137). It marks a particular record, not the latest one. Only the
  interval containing the date is used.
- **9,535 of 96,826 interval rows carry sentinel codes** (`0`, `9999`, empty),
  clustering on end-of-life stubs -- PERMNO 10001's final one-day record is
  `SICCD = 0` at delisting. The prior interval's code is carried forward; a
  later interval is never consulted.

Limitation this export cannot resolve: time-varying structure proves the field
is not uniformly backfilled, but not that a reclassification was recorded when
it became publicly known rather than at its effective date.

## 2. Exposures (W5-002)

Three exposures, all determined by the close of t-1, matching the rule every
factor already obeys:

| exposure | definition | coverage on aligned rows |
|---|---|---|
| `sector` | SIC division, 10 divisions plus a catch-all | 100.0% |
| `beta_252` | rolling market beta, window ending t-1 | 100.0% |
| `log_mcap` | log market cap at t-1 | 100.0% |

Coverage is exactly complete, which is not an accident: Week 1 eligibility
already requires 252 prior valid returns, which is precisely what the beta
window needs. 9 to 11 sectors are present per date, so division-level
granularity avoids thin buckets -- 81 two-digit SIC groups against ~1,660 names
per date would have been ~20 names per bucket, too thin to residualise against.

Sector is looked up on the trading calendar's previous date rather than the
stock's own previous row, since SIC intervals are keyed to calendar time. A
stock returning from a trading gap therefore gets its correct classification
rather than a stale one.

`beta_252` on the aligned panel runs from -10.9 to +7.1 with a mean of 1.20, so
it and `log_mcap` are winsorised cross-sectionally at the 1st/99th percentile
before being regressed against, following the convention already used for IC.

Five tests pin these, including the same at-or-after-t perturbation test the six
factors pass, and a test that the header row is not consulted.

## 3. Neutralisation fails its pre-declared test in 7 of 8 books (W5-003)

Each score is residualised per date against sector dummies plus winsorised
`beta_252` and `log_mcap`, the residual is ranked, and the unchanged continuous
backtest is rerun. The raw side reproduces Week 4 exactly, confirming nothing
leaked into the shared machinery.

The criterion, fixed in advance: **realised beta materially closer to zero AND
net Sharpe at 10 bp no worse than raw.** Lowering beta by destroying return is
a failure, not a win.

| book | gross SR raw -> neut | HAC t | net@10bp raw -> neut | beta raw -> neut | verdict |
|---|---|---|---|---|---|
| `composite__decile` | 0.297 -> **0.486** | 0.99 -> **1.53** | +0.155 -> **+0.209** | -0.266 -> -0.057 | **PASS** |
| `composite` | 0.297 -> 0.358 | 1.01 -> 1.17 | +0.163 -> +0.081 | -0.187 -> -0.038 | FAIL |
| `gbm__decile` | 0.099 -> 0.193 | 0.32 -> 0.59 | -0.069 -> -0.144 | -0.220 -> -0.006 | FAIL |
| `ridge__decile` | 0.100 -> 0.208 | 0.31 -> 0.63 | -0.127 -> -0.216 | -0.206 -> -0.047 | FAIL |
| `ols__decile` | 0.096 -> 0.208 | 0.29 -> 0.62 | -0.132 -> -0.216 | -0.206 -> -0.047 | FAIL |
| `ridge` | 0.085 -> 0.229 | 0.26 -> 0.68 | -0.165 -> -0.291 | -0.136 -> -0.030 | FAIL |
| `ols` | 0.084 -> 0.226 | 0.26 -> 0.67 | -0.167 -> -0.293 | -0.135 -> -0.030 | FAIL |
| `gbm` | 0.098 -> 0.072 | 0.32 -> 0.22 | -0.086 -> -0.340 | -0.138 -> +0.017 | FAIL |

**Beta is not what fails.** Every book sheds 75-98% of its realised market beta;
`gbm` under rank weighting crosses zero. The first leg passes everywhere. What
fails, in seven books, is the second leg: net Sharpe at 10 bp gets worse.

### 3a. Why: the cost is charged against a halved risk budget

The obvious explanation would be that neutralisation trades more. It does not --
turnover moves by 1 to 7% at most. Measured on the composite:

| | raw | neutralised | ratio |
|---|---|---|---|
| annualised volatility | 8.43% | 4.12% | **0.49** |
| annualised gross return | 2.50% | 1.48% | 0.59 |
| annualised cost drag at 10 bp | 1.13% | 1.14% | **1.01** |
| annual turnover | 5.64x | 5.72x | 1.01 |
| gross Sharpe | 0.297 | 0.358 | 1.21 |
| **net Sharpe at 10 bp** | **0.163** | **0.081** | **0.49** |

Stripping the market-driven variance halves the volatility while the dollar cost
of trading stays exactly where it was. Gross Sharpe improves, because return
falls less than risk does. But cost is a fixed charge in return units, so
dividing it by a halved denominator doubles its bite in Sharpe terms.
Neutralisation shrank the risk budget the same trading bill is charged against.

This cannot be levered away. Scaling the book scales returns, turnover and
therefore costs together, so net Sharpe is leverage-invariant.

That is the textbook failure mode "lowers beta by destroying return", arriving
through the denominator rather than the numerator, and it is only visible
because the success criterion was written in net terms in advance. Judged on
gross Sharpe alone, `ols` and `ridge` nearly *tripled* and neutralisation would
have been recorded as a clear win.

### 3b. What the books actually shed

For the rank composite: `beta_252` exposure -0.168 to -0.001 and `log_mcap`
0.148 to 0.010, both essentially zeroed as designed; sector tilt falls 84%. Of
the six factors, `rvol_20` (-62%) and `dd_252` (-35%) drop most -- the two Week 3
flagged as 0.87-correlated, both carrying their own negative beta -- while
`mom_120_20`, `rmom_120_20`, `rev_5` and `vs_20` move 5-45%. So neutralisation
partly defuses the Week 3/Week 4 correlated cluster, but only as a side effect
of removing beta, and it does not eliminate it.

## 4. Ablation (W5-004)

Leave-one-out over the six factors, both weightings, identical estimator:

- **Not redundant**: `mom_120_20` and `rev_5`. Dropping either lowers net Sharpe
  at 10 bp under both weightings.
- **Redundant by the pre-declared rule**: `rmom_120_20` and `vs_20`. Dropping
  either is flat-to-better both ways. Of the momentum pair Week 3 flagged as
  0.76-correlated, momentum is the half the composite needs and residual
  momentum is the spare -- consistent with Week 4's exposure table, where
  momentum carried 0.471 against residual momentum's 0.355.
- **Inconclusive**: `rvol_20` and `dd_252`, the 0.87-correlated pair. Dropping
  either hurts the rank book and helps the decile book. That is a weighting
  artefact, not a redundancy signal.

Every ablated book sits at HAC `|t|` between 0.81 and 1.29. None of these
differences is distinguishable from the others or from zero, and per the
pre-declared rule nothing is dropped on ablation evidence alone.

## 5. Robustness (W5-005)

**Volatility regimes and sub-periods: this is what slicing noise looks like.**
The low-volatility tercile shows HAC `t` = 2.43 and calendar 2018 shows 2.21.
Neither is a finding. Each is the best of a set of ex-post, non-pre-specified
slices -- roughly six and ten respectively -- carved out of a series whose
full-sample `t` is 1.0. The 20-day cohort overlap means a tercile's 832 days is
closer to 40 independent observations than 832. And the tercile boundaries come
from a full-sample quantile split, so the regime rule is not even implementable
in real time: it is a descriptive diagnostic, not a tradable signal. Mid and
high terciles are at `|t| < 0.5`. Pre-half `t` is 1.77 and post-half 0.18, which
is within what sampling noise produces on a `t` = 1 series.

**Cost curve** reproduces the known breakeven exactly: 22.2 bp rank, 20.9 bp
decile.

**Rebalance horizon is where the study's cost claim proves fragile.** Across the
pre-declared set {5, 10, 20, 40} trading days:

| horizon | gross SR | HAC t | net@10bp | turnover/yr | breakeven bp |
|---|---|---|---|---|---|
| 5 | 0.383 | 1.27 | +0.016 | 16.0 | 10.4 |
| 10 | 0.326 | 1.10 | +0.112 | 9.3 | 15.2 |
| 20 | 0.297 | 1.01 | +0.163 | 5.6 | 22.2 |
| 40 | 0.306 | 1.04 | +0.226 | 3.2 | 38.5 |

Gross Sharpe barely moves and every HAC `t` stays in 1.00-1.27, so no horizon is
significant and gross performance is not monotonic in horizon. But breakeven
swings 10.4 to 38.5 bp -- a factor of 3.7 -- almost entirely because turnover
falls fivefold. **The breakeven figure this project has been quoting is an
artefact of an arbitrary, equally defensible holding-period choice.** That is a
limitation of the headline claim, not an argument for the 40-day book, and no
horizon is recommended.

## 6. The locked specification (W5-006)

Rule, fixed in advance: maximise net Sharpe at 10 bp subject to realised market
beta within 0.10 of zero. Applied mechanically to all 28 candidate books from
Weeks 3 to 5 -- raw, neutralised, and every ablated variant.

**Only 8 of 28 pass the beta constraint, and all 8 are neutralised.** Three raw
ablated composites had competitive net Sharpe (+0.183, +0.183, +0.174) and were
disqualified on beta alone, which is exactly what the constraint was written to
do.

**Locked: `composite__decile__neutral`.**

| property | value |
|---|---|
| factors | all six, equal-weighted signed ranks |
| neutralisation | sector, `beta_252`, `log_mcap`, cross-sectional, per date |
| weighting | tail decile, +1/0/-1 |
| holding period | 20 trading days, staggered daily cohorts |
| construction | dollar-neutral, 1% position cap |
| realised beta | -0.057 |
| gross Sharpe | 0.486 (HAC t 1.53) |
| net Sharpe at 10 bp | +0.209 |

Recorded in `reports/week5/locked_specification.json`.

**This lock is a procedural commitment, not a claim of edge.** A HAC `t` of 1.53
is a two-sided p of about 0.13. It is the highest figure the whole Weeks 3-5
program has produced -- the previous ceiling was 1.01 -- and it is still not
significant. Its own mean rank IC roughly halved under neutralisation, 0.0354 to
0.0133. The specification is locked so that Week 6 is a genuine test rather than
a search, and the honest prior going in is that the final result will be
indistinguishable from zero.

## 7. Limitations

- Everything in Weeks 3-5 remains statistically indistinguishable from zero. The
  locked book's HAC `t` of 1.53 is the best in the program and does not clear
  conventional significance.
- The selection rule ran over 28 candidate books. Even with the rule declared in
  advance, the winner is the maximum of 8 admissible correlated estimates, and
  no multiple-testing correction is applied to it.
- Sector is point-in-time in structure, but this export cannot confirm that a
  reclassification was recorded when publicly known rather than at its effective
  date.
- The volatility-regime split uses full-sample tercile boundaries and is
  descriptive only.
- Breakeven cost is fragile to holding period, swinging 3.7x across four
  defensible horizons (section 5).
- Neutralisation removes beta, size and sector but only partly defuses the
  correlated factor cluster identified in Week 3.
- The delisting-return limitation from Week 1 stands: this export has no
  explicit delisting-return field, so incomplete post-exit target windows are
  censored.

## 8. What Week 6 does

Open 2024-2025 exactly once, run the locked specification above unchanged, and
report the result whatever it is. No re-selection, no re-tuning, no second look.

If the out-of-sample result is positive, it will still be one draw from a
distribution whose in-sample centre could not be distinguished from zero. If it
is negative, that is the more likely outcome given everything above, and it will
be reported as the project's finding rather than explained away.
