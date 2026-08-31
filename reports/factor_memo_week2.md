# Week 2 factor-research memo — six single-factor signals

**Date:** 2026-08-31
**Experiments:** `W2-001` … `W2-008`
**Evaluation sample:** 2006-01-03 to 2023-11-30 (4,509 dates, ~1,635 names/date)
**Final test 2024–2025: not touched.**

Reproduce with:

```
python src/evaluation/factor_eval.py            # all six
python src/evaluation/factor_eval.py rvol_20    # or one
```

Per-factor outputs are in `reports/factor_<name>/`; the cross-factor table is
`reports/factor_summary.csv`. This memo supersedes the portfolio numbers in
`factor_memo_01_momentum.md` (see §7).

---

## 1. What was tested

Six signals, each with its window and its predicted sign fixed **before** the
factor was evaluated, and each evaluated exactly once. No window was searched
and no factor was re-tuned after seeing a result.

| Factor | Definition | Predicted sign |
|---|---|---|
| `mom_120_20` | compounded return over *t*−120 … *t*−21 | + winners keep winning |
| `rev_5` | −Σ of the last five daily returns | + recent losers bounce |
| `rvol_20` | √Σ of squared returns over *t*−20 … *t*−1 | − high volatility underperforms |
| `vs_20` | log(turnover at *t*−1 ÷ its mean over *t*−21 … *t*−2) | + high-volume return premium |
| `rmom_120_20` | Σ market-model residuals over *t*−120 … *t*−21, fit over the 252 days ending *t*−21 | + momentum in residuals |
| `dd_252` | fall at *t*−1 from the peak of the cumulative total-return index over *t*−252 … *t*−1 | + proximity to the 52-week high |

All six run through one harness: same universe, same 20-day target, same
per-date winsorisation and ranking, same portfolio rule, same cost grid. Only
`FACTOR_SQL` and `FACTOR_SIGN` differ between them, so cross-factor differences
are differences in the signal, not in the measurement.

### Two data facts that shaped the definitions

In this CRSP export, `ret` is split-adjusted but `price`, `volume` and
`shares_outstanding` are **as-traded**. Verified directly on Apple's 7:1 split
of 2014-06-09: price 645.57 → 93.70 and volume 12.5m → 75.4m across one day,
while the return is a normal +1.6%.

Two factors would have been silently wrong had this gone unchecked:

- **Volume surprise** uses share **turnover** (volume ÷ shares outstanding), not
  share volume. A split multiplies both and cancels out of the ratio. Raw
  volume would have produced a spurious log(7) ≈ +1.95 spike lasting 20 days
  after every split.
- **Drawdown** is measured on a cumulative **total-return index**, not on a
  price level. A raw price would have shown a false −86% drawdown for a year
  after every 7:1 split.

Both are covered by tests that apply a synthetic 7:1 split and assert the factor
does not move.

## 2. Timing: every factor is known at the close of *t*−1

The target is the return from the close of *t* to the close of *t*+20. A signal
that still needs *t*'s own close could therefore only be executed at that same
close — the position would have to be established at the instant the return
starts accruing. Every factor here ends its last input at *t*−1, leaving a full
trading day between the signal and the start of the target.

This was a correction. `vs_20` and `dd_252` were originally defined on day-*t*
turnover and day-*t* drawdown, which is timing-legal against a *t*+1 target but
implicitly assumes same-close execution. Both were lagged one day and rerun
(`W2-008`); §4 reports what that cost.

The shared leakage test now perturbs every input column on every row from *t*
onwards — not merely after *t* — and asserts all six factors are unchanged at
*t*. Every factor also asserts window completeness, both the count of observed
inputs and the earliest trading-day index, so a stock with a gap in its history
returns NULL rather than a silently short-window value.

The sealed period is enforced on the **target window**, not the observation
date: the last evaluated date is 2023-11-30, the last date whose 20-day forward
window still ends inside 2023.

## 3. Coverage

Coverage is ≥99.7% for five factors. `rmom_120_20` averages 98.98% with 20 dates
at exactly zero: it needs 273 trading days of history, while eligibility only
requires 252, so no stock qualifies during the first 20 trading days of 2006
(2006-01-03 to 2006-01-31). After 2006-01-31 its coverage is 99.4%. This is a
sample-start artefact, not a data defect.

## 4. Information coefficients

Daily cross-sectional IC, 2006–2023. Targets overlap 20 days, so the t-statistic
is Newey-West with 20 lags; the naive daily ICIR is not a valid significance
statistic and is not shown here.

| Factor | Mean rank IC | Signed | NW(20) t | Mean Pearson IC | NW(20) t | SD rank IC | Neg. years |
|---|---|---|---|---|---|---|---|
| `mom_120_20` | −0.00002 | −0.00002 | −0.00 | 0.0056 | 0.73 | 0.149 | 8 / 18 |
| `rev_5` | 0.0077 | 0.0077 | 2.12 | 0.0063 | 1.81 | 0.117 | 6 / 18 |
| `rvol_20` | −0.0286 | **0.0286** | **−2.85** | −0.0202 | −2.25 | 0.188 | 5 / 18 |
| `vs_20` | 0.0039 | 0.0039 | 2.50 | 0.0032 | 2.28 | 0.049 | 6 / 18 |
| `rmom_120_20` | −0.0036 | −0.0036 | −0.63 | 0.0021 | 0.39 | 0.107 | 12 / 18 |
| `dd_252` | 0.0155 | 0.0155 | 1.44 | 0.0164 | 1.55 | 0.197 | 5 / 18 |

"Signed" applies the pre-registered sign, so a positive value means the factor
worked in the predicted direction. "Neg. years" counts calendar years in which
the signed mean rank IC was negative.

**Only realised volatility survives a multiple-testing correction.** With six
tests the Bonferroni critical value at 5% is |t| ≈ 2.64. `rvol_20` clears it at
2.85. `vs_20` (2.50) and `rev_5` (2.12) are individually significant but do not
clear it. `dd_252` is suggestive and insignificant. `mom_120_20` is a clean
zero, and `rmom_120_20` is a zero with the **wrong sign** — negative in 12 of 18
years, so removing the market component did not rescue the momentum effect, it
removed what little was left.

### What the one-day lag cost

| `vs_20` | Same-close (original) | Lagged to *t*−1 |
|---|---|---|
| Signed rank IC | 0.0056 | 0.0039 |
| NW(20) t | 3.43 | 2.50 |
| Gross Sharpe | 0.344 | 0.256 |
| Breakeven cost | 5.6 bp | 4.1 bp |

**About a third of volume surprise's apparent predictive power required trading
at the same close that produced the signal.** That is the difference between the
strongest-looking factor in the study and one that no longer survives a
correction for the six tests run. `dd_252` was almost unaffected (t 1.39 → 1.44,
gross Sharpe 0.032 → 0.044), which is what a slow-moving one-year variable
should do. The contrast is itself informative: the more of a signal's content
sits in the most recent observation, the more of it is an execution assumption.

## 5. Quantile returns — the cross-cutting result

Mean 20-day forward return by decile of the raw factor, in percent. Deciles are
by ascending factor value, so decile 10 is the highest-momentum, most-volatile,
highest-volume-surprise, smallest-drawdown stock. The equal-weighted universe
mean is ≈0.84% per 20 days.

| Factor | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|---|
| `mom_120_20` | 0.54 | 0.86 | 0.99 | 0.92 | 0.93 | 0.90 | 0.84 | 0.78 | 0.78 | 0.81 |
| `rev_5` | 0.57 | 0.73 | 0.81 | 0.84 | 0.88 | 0.91 | 0.92 | 0.95 | **0.96** | 0.78 |
| `rvol_20` | 0.79 | 0.90 | 0.92 | 0.93 | 0.93 | 0.94 | 0.88 | 0.84 | 0.78 | **0.45** |
| `vs_20` | 0.65 | 0.81 | 0.86 | 0.86 | 0.89 | 0.89 | 0.88 | 0.85 | 0.86 | 0.80 |
| `rmom_120_20` | 0.66 | 0.88 | 0.91 | 0.91 | 0.90 | 0.87 | 0.83 | 0.81 | 0.86 | 0.73 |
| `dd_252` | 0.59 | 0.78 | 0.88 | **0.99** | 0.93 | 0.89 | 0.87 | 0.89 | 0.85 | 0.69 |

**Not one of the six is monotone across all ten deciles, and five of six are
hump-shaped: both extremes underperform the interior.** This is the most useful
thing Week 2 produced, and it has three consequences.

1. **Decile-spread portfolios sit on the two buckets where the relationship
   breaks.** `rev_5` is the clearest case: it rises monotonically from D1
   (0.57%) to D9 (0.96%), then D10 — the most extreme five-day losers —
   collapses to 0.78%. The long leg of the long-short book is precisely the one
   bucket that fails.
2. **`rvol_20` is a short, not a spread.** Its D1 (0.79%) is *below* the
   interior peak (0.94% at D6). There is no low-volatility premium here in the
   usual sense; the entire effect is that the top volatility decile returns
   0.45%, roughly half the universe mean. The same holds for `dd_252`: the
   deepest-drawdown decile earns 0.59% and stocks sitting at their 52-week high
   earn 0.69%, while the interior peaks at 0.99%.
3. **The six are probably not six bets.** D1 is the worst or near-worst decile
   for every factor, and for momentum, volatility, drawdown and residual
   momentum that bucket is largely the same population of distressed,
   high-volatility names. The apparent spreads may be one exposure counted
   several times. Week 3 measures the cross-factor correlations directly; Week 5
   neutralisation is the test.

**Rank-based continuous weights are not a fix for this.** Weights linear in
cross-sectional rank still put their largest magnitudes on the same extreme
buckets that break down. They are adopted in Week 3 as the pre-declared
baseline because they use the whole cross-section and are the simplest rule to
state, not because they are expected to outperform tail deciles here.

## 6. Persistence, turnover and cost

| Factor | Rank autocorr 1d | 20d | Turnover / rebalance | Gross Sharpe | Breakeven cost |
|---|---|---|---|---|---|
| `mom_120_20` | 0.987 | 0.768 | 0.896 | 0.147 | **14.9 bp** |
| `rev_5` | 0.759 | −0.003 | 1.736 | 0.149 | 6.0 bp |
| `rvol_20` | 0.983 | 0.658 | 1.218 | 0.161 | **14.0 bp** |
| `vs_20` | 0.480 | −0.089 | 1.842 | 0.256 | 4.1 bp |
| `rmom_120_20` | 0.983 | 0.708 | 0.977 | 0.059 | 3.7 bp |
| `dd_252` | 0.983 | 0.806 | 1.001 | 0.044 | 5.0 bp |

Gross and net Sharpe, averaged over all 20 rebalance offsets:

| Factor | Gross | 1 bp | 5 bp | 10 bp | 20 bp |
|---|---|---|---|---|---|
| `mom_120_20` | 0.147 | 0.137 | 0.098 | 0.048 | −0.050 |
| `rev_5` | 0.149 | 0.123 | 0.020 | −0.108 | −0.365 |
| `rvol_20` | 0.161 | 0.149 | 0.104 | 0.047 | −0.067 |
| `vs_20` | 0.256 | 0.194 | −0.057 | −0.370 | −0.996 |
| `rmom_120_20` | 0.059 | 0.043 | −0.020 | −0.099 | −0.257 |
| `dd_252` | 0.044 | 0.036 | 0.002 | −0.042 | −0.128 |

**The factor with the best gross Sharpe is still the least usable.** `vs_20`
leads on gross Sharpe (0.256) and dies fastest: turnover of 1.84 per rebalance —
essentially a full rotation — puts its breakeven at 4.1 bp and its net Sharpe at
−0.37 by 10 bp. `rev_5` behaves the same way. Meanwhile momentum, whose IC is
exactly zero, has the second-highest breakeven simply because it barely trades.

**Not one of the six is viable at 20 bp, and only two are positive at 10 bp.**
At 5 bp four of six are still positive but none exceeds a Sharpe of 0.11.

Rank autocorrelation tracks turnover as expected, but the relationship is not
tight: `mom_120_20` and `dd_252` have nearly identical 1-day autocorrelation
(0.987 vs 0.983) and similar turnover, yet `rvol_20`, with the same 1-day
persistence, turns over 22% more. The diagnostic that actually predicts cost is
20-day autocorrelation at the tails, not average rank stability.

## 7. Rebalance-offset sensitivity — a correction

A non-overlapping 20-day rebalance can start on any of 20 trading-day offsets.
The first version of this analysis reported a single offset. At these turnover
levels that is not a stable estimator:

| Factor | Gross Sharpe: mean | min offset | max offset | SD |
|---|---|---|---|---|
| `mom_120_20` | 0.147 | 0.055 | 0.231 | 0.046 |
| `rev_5` | 0.149 | **−0.315** | **0.547** | 0.233 |
| `rvol_20` | 0.161 | 0.052 | 0.266 | 0.054 |
| `vs_20` | 0.256 | −0.086 | 0.672 | 0.200 |
| `rmom_120_20` | 0.059 | −0.095 | 0.184 | 0.083 |
| `dd_252` | 0.044 | −0.044 | 0.137 | 0.050 |

For `rev_5` the offset choice spans −0.32 to +0.55. Offset 0 — the one an
obvious implementation picks — happened to be the worst of the twenty, which is
why an earlier run showed reversal with a *negative* gross Sharpe despite a
significantly positive IC. All portfolio statistics in this memo are averaged
over all 20 offsets, and the spread is reported above as sampling uncertainty.

The high-turnover factors are exactly the ones with the widest offset spread,
which is the same phenomenon as their cost sensitivity: when a book rotates
almost completely each period, which period you are on matters. Week 3 replaces
this estimator with staggered daily cohorts, which uses every start date at once.

Two other corrections applied since the momentum memo:

- **Maximum drawdown** now floors the running peak at the starting wealth of
  1.0, so a loss before any new high is counted. Previously an initial decline
  registered as zero drawdown.
- The momentum figures in `factor_memo_01_momentum.md` §7 are superseded:
  gross Sharpe 0.188 → **0.147**, net at 10 bp 0.088 → **0.048**, breakeven
  ≈19 bp → **≈14.9 bp**. The IC, decile, coverage and persistence results in
  that memo are unchanged, as are its conclusions. Momentum was not re-tuned;
  only the estimator changed.

## 8. Limitations

- **Delisting returns.** The export has no delisting-return field, so targets
  spanning a stock's exit are censored (Week 1). This biases against observing
  the worst outcomes, which cluster in the D1 buckets that drive most of these
  spreads. True spreads are plausibly wider than reported; the direction is
  known, the magnitude is not.
- **No neutralisation.** These are raw factors. §5 gives direct reason to think
  several of them load on the same distress/volatility exposure.
- **Equal weighting inside deciles** loads on the smallest eligible names, which
  are the most expensive to trade, so realised costs would exceed the flat
  per-unit assumption.
- **Six tests.** Bonferroni is applied above, but the six factors were chosen
  from published literature, so the effective number of hypotheses behind them
  is larger than six and cannot be counted.
- **`rmom_120_20` estimates one market model per stock-date** over 252 days with
  no shrinkage and no robustness to outliers, and uses in-sample residuals from
  the estimation window. That is the standard construction, but a noisy beta
  will show up as noise in the factor.
- **Execution is still idealised.** The one-day lag makes the signals executable
  in principle during day *t*, but the target is a close-to-close return, so the
  implicit assumption is execution at the close of *t* at no impact. Nothing here
  models participation, spread or impact.

## 9. Decisions

**All six factors are kept for the Week 3/4 multi-factor work**, with the
following understanding recorded now, before any model is fitted:

| Factor | Status |
|---|---|
| `rvol_20` | Only factor surviving Bonferroni; breakeven 14 bp. Best single candidate. |
| `vs_20` | Individually significant, does not survive the correction, and breakeven 4.1 bp. Keep, but not as a standalone. |
| `rev_5` | Positive IC, does not survive the correction, extreme offset sensitivity. Keep with caution. |
| `dd_252` | Insignificant on its own; interesting hump shape. Keep as a control. |
| `mom_120_20` | Documented null. Keep for the ablation and as a control. |
| `rmom_120_20` | Null with the wrong sign in 12 of 18 years. Keep only for the ablation. |

No factor definition changes as a result of these numbers. Re-tuning a window
after seeing its IC is the researcher-degrees-of-freedom problem §15 of the plan
warns about, and it would invalidate the sealed test.

**Three findings should drive Week 3 design**, not just be reported:

1. Report portfolio statistics over staggered cohorts rather than one rebalance
   offset. §7 shows a single offset can flip a sign.
2. Treat rank-based continuous weights as the pre-declared baseline, not as a
   remedy for §5. They still emphasise the extremes.
3. Measure the cross-factor correlation structure before combining anything.
   §5.3 suggests four of the six may be one exposure.

**Open question for Week 5:** whether `rvol_20`, `dd_252`, `mom_120_20` and
`rmom_120_20` are four signals or one. Their D1 buckets look like the same
stocks.
