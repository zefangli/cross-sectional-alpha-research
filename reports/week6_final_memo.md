# Week 6: The sealed final test

Date: 2026-09-11. Experiment: W6-001. Run once, at commit `084f5eb`, against the
specification locked at `fbbe574` in `reports/week5/locked_specification.json`.

The sealed period was opened exactly once. The specification was not changed
before, during or after. No model, filter, factor or sub-period was introduced
for this memo.

## 1. What was run

`drop_rmom_120_20__neutral__decile`, locked in Week 5 by a rule declared before
any Week 5 result existed and applied mechanically to a 40-book candidate grid:

| property | value |
|---|---|
| factors | `mom_120_20` +1, `rev_5` +1, `rvol_20` -1, `vs_20` +1, `dd_252` +1 |
| dropped | `rmom_120_20` |
| neutralisation | sector dummies, winsorised `beta_252` and `log_mcap`, per date |
| weighting | tail decile |
| holding period | 20 trading days, staggered daily cohorts |
| construction | dollar-neutral, 1% position cap |

Formation 2024-01-02 to 2025-12-02; P&L 2024-01-03 to 2025-12-31; 501 trading
days; rank IC measured on the 482 formation dates.

## 2. The result

| metric | 2014-2023 (in-sample) | **2024-2025 (sealed)** |
|---|---|---|
| gross Sharpe | 0.534 | **1.522** |
| HAC t on mean daily gross return | 1.65 | **2.76** |
| net Sharpe at 1 bp | -- | 1.491 |
| net Sharpe at 5 bp | -- | 1.368 |
| **net Sharpe at 10 bp** | **0.238** | **1.215** |
| net Sharpe at 20 bp | -- | 0.909 |
| breakeven cost | 18.0 bp | **49.7 bp** |
| annualised gross return | -- | 8.80% |
| annualised volatility | -- | 5.78% |
| max drawdown | -17.8% | -4.1% |
| realised market beta | -0.056 | -0.065 |
| annual turnover | 9.03x | 8.86x |
| mean rank IC | -- | 0.0364 (HAC t 4.63) |

The locked book was profitable out of sample, after costs, at every cost tier
tested, with a realised market beta of -0.065 -- inside the 0.10 constraint the
selection rule imposed in sample, which it had no obligation to honour out of
sample.

Under the null of zero Sharpe the statistic is `t` = 2.15 naive and **2.76 with
Newey-West at 20 lags** (the staggered cohorts induce serial dependence; the HAC
figure is the one to read). That is a nominal two-sided p of about 0.006. Rank
IC is 0.0364 with a HAC `t` of 4.63.

This is the strongest form of evidence this project can produce: a
pre-registered specification, frozen in a committed artefact, executed once
against data never previously evaluated.

## 3. What this does and does not establish

**It is not significantly better than the in-sample estimate.** Out-of-sample
Sharpe is 1.52 against 0.534 in sample. The difference is +0.99 with a standard
error of about 1.10, so `t` is 0.90. A tripling looks dramatic and is entirely
consistent with sampling noise on two years of data. Out-of-sample results
usually *degrade*; this one improved, and a large favourable surprise warrants
more scepticism than a small one, not less.

**The point estimate is imprecise.** Two years is 1.99 years of data. An
approximate 95% interval around the Sharpe of 1.52 runs roughly -0.5 to 3.6. The
hypothesis test and the estimate say different things and both are correct: the
mean return is distinguishable from zero, while the *magnitude* is barely
pinned down at all. Any forward-looking use of 1.52 as an expectation would be
unsupported by this evidence.

**The specification was selected, and selection is not corrected for.** The
locked book is the maximum of 20 admissible correlated candidates under a rule
fixed in advance. Pre-registration makes the out-of-sample test valid as a
single test; it does not make the *expected* out-of-sample performance equal to
the in-sample point estimate, and selection normally biases that expectation
downward. That it came in higher is not explained by selection.

**Two years is one regime.** Both calendar years are positive (2024 Sharpe 1.39,
HAC `t` 1.73; 2025 Sharpe 1.65, HAC `t` 2.22), reported here descriptively with
neither preferred. This is consistency, not independent confirmation: two
adjacent years of one market are not two experiments.

**The cost claim remains horizon-fragile.** Breakeven is 49.7 bp out of sample
against 18.0 bp in sample. W5-005 established that breakeven swings by a factor
of 3.7 across four equally defensible holding periods while gross Sharpe barely
moves. The 20-day horizon was fixed in Week 0 and not tuned, but the breakeven
figure should be read as horizon-dependent, not as a property of the signal.

**The dropped factor is still in the book.** Mean exposure to `rmom_120_20` is
0.248 despite its exclusion from the factor set, because the five retained
factors correlate with it. Dropping a factor removes it as an input, not as an
exposure. The book's largest factor exposures out of sample remain
`mom_120_20` (0.443) and `dd_252` (0.355) -- the same correlated cluster
identified in Week 3 and never fully defused.

**Residual exposures are small but non-zero**: `beta_252` 0.017, `log_mcap`
0.018, sector 0.083. Neutralisation is measured at formation; the book drifts
over its 20-day hold.

## 4. Standing limitations, unchanged by this result

- The universe carries the Week 1 delisting-return limitation: this export has
  no explicit delisting-return field, so incomplete post-exit target windows are
  censored. Survivorship effects are reduced but not eliminated.
- Costs are a flat per-notional assumption. No market-impact model, no
  borrow cost, no short availability constraint, no capacity analysis. The
  1% position cap never binds, so the book is untested at size.
- The sealed period is outcome-sealed but was not literally untouched: exposures
  were built over full panel history, and an early exposure audit summarised
  2024-2025 covariate rows. No sealed-period return, target or performance
  figure was computed before this run. See W5-009.
- One dataset, one country, one asset class, one twenty-year window.

## 5. Conclusion

A pre-registered, cost-aware, risk-neutralised five-factor book earned a gross
Sharpe of 1.52 and a net Sharpe at 10 bp of 1.22 over a sealed two-year period,
with a HAC `t` of 2.76 and a realised market beta of -0.065.

The correct reading is narrow. The result is real, it was obtained under
genuine out-of-sample conditions, and it is nominally significant. It is also
two years long, imprecisely estimated, statistically indistinguishable from the
much weaker in-sample estimate, and produced by a specification chosen as the
best of twenty. Weeks 2 through 5 found essentially nothing distinguishable from
zero; one favourable two-year draw does not overturn that, and the honest
summary of the whole project is a weak signal that survived a fair test once.

What would change the conclusion is more out-of-sample time, not more analysis
of these two years. The specification stays locked. This test is not repeatable
on this data.
