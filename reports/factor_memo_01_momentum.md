# Factor memo 01 — medium-term momentum (`mom_120_20`)

**Date:** 2026-08-30
**Experiment:** `W2-001`
**Evaluation sample:** 2006-01-03 to 2023-11-30 (4,509 dates)
**Final test 2024–2025: not touched.**

Reproduce with:

```
python src/evaluation/factor_eval.py mom_120_20
```

Outputs land in `reports/factor_mom_120_20/` (`daily.csv`, `deciles.csv`,
`portfolio.csv`, `yearly.csv`, `summary.csv`, `diagnostics.png`).

---

## 1. Hypothesis

Stocks that outperformed over the past six months, excluding the most recent
month, continue to outperform over the next 20 trading days, in the
cross-section of liquid U.S. common equity. The one-month skip is intended to
separate the effect from short-term reversal.

$$
MOM_{120,20} = \prod_{k=21}^{120}\left(1+r_{t-k}\right)-1
$$

Predicted sign: positive. Pre-registered in `research_protocol.md` as signal 1;
the window was fixed before any evaluation was run.

## 2. Design

- **Universe:** the point-in-time eligible panel from Week 1 — U.S. common
  equity on NYSE/AMEX/Nasdaq, price ≥ $5, 20-day average dollar volume ≥ $5m,
  ≥ 252 prior valid returns. Averages 1,638 names per date.
- **Target:** 20-trading-day forward total return, only where all 20 returns are
  observed (Week 1 censoring rule).
- **Window completeness:** the factor is `NULL` unless all 100 returns from
  *t*−120 to *t*−21 are present *and* those rows are 100 consecutive trading
  days. A stock with a gap gets no value rather than a short-window value.
- **Sealed-period rule:** the last evaluated date is the last one whose forward
  window still ends on or before 2023-12-31, which is 2023-11-30. No return
  realised in 2024 enters any statistic in this memo.
- **Preprocessing:** per date, winsorise the factor at the 1st/99th
  cross-sectional percentiles (Pearson IC) and rank within date (Spearman IC).
  All parameters are estimated within the date, so nothing crosses time.
- **Portfolio:** equal-weighted long decile 10, short decile 1, rebuilt on
  **non-overlapping** 20-trading-day rebalance dates (226 rebalances) so holding
  periods never overlap. Weights sum to +1 long and −1 short, gross leverage 2.
- **Turnover convention:** $TO_t=\tfrac12\sum_i|w_{i,t}-w_{i,t-1}|$, so a full
  rotation is $TO=2$ and traded notional is $2\,TO$. Costs are charged on traded
  notional: $R^{net}=R^{gross}-2c\,TO$. The first rebalance pays the cost of
  building the book from cash.
- **Inference:** daily IC series are computed on overlapping 20-day targets, so
  the mean IC t-statistic uses Newey-West with 20 lags. The naive daily ICIR is
  reported too, but it is not a valid significance statistic here.

## 3. Coverage

| Metric | Value |
|---|---|
| Dates | 4,509 |
| Mean names per date | 1,638 |
| Mean coverage (eligible rows with a factor value) | 99.89% |
| Minimum daily coverage | 99.57% |

Coverage is effectively complete: the 252-prior-return eligibility screen
already guarantees the 120-day history the factor needs, so the two screens
almost fully overlap. Coverage will be a more informative diagnostic for the
volume-surprise and residual-momentum factors.

## 4. Information coefficient

| Metric | Pearson | Spearman |
|---|---|---|
| Mean IC | 0.00563 | −0.00002 |
| SD of IC | 0.1439 | 0.1485 |
| Daily ICIR (not a t-stat) | 0.039 | −0.0001 |
| Newey-West(20) t-stat | **0.73** | **−0.00** |
| Share of days with IC > 0 | — | 52.8% |

**The signal is indistinguishable from zero.** Pearson IC is slightly positive,
rank IC is exactly flat, and neither is close to significant once the 20-day
target overlap is accounted for. The daily IC distribution is wide
(5th/95th percentile −0.246 / +0.222) and mildly left-skewed (−0.43): momentum's
bad days are worse than its good days are good.

Rolling 252-day mean rank IC (`diagnostics.png`, top-left) oscillates between
roughly −0.12 and +0.09 and changes sign repeatedly. Annually
(`yearly.csv`), mean rank IC is negative in **8 of 18 years**. There is no
period of more than about two years in which the sign is stable.

## 5. Quantile returns

Mean 20-trading-day forward return by factor decile (decile 10 = highest past
momentum), averaged across dates:

| Decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Mean 20d return | 0.54% | 0.86% | 0.99% | 0.92% | 0.93% | 0.90% | 0.84% | 0.78% | 0.78% | 0.81% |

**The pattern is not monotonic — it is a hump.** Returns rise from decile 1 to
decile 3, then decline gently through decile 10. The D10−D1 spread of +0.27% per
20 days (≈3.4% annualised) comes almost entirely from decile 1 underperforming,
not from decile 10 outperforming; deciles 3–6 beat decile 10.

Decile 1 also has by far the highest dispersion of date-level mean returns
(SD 0.092 versus 0.056–0.071 elsewhere). A long-short book built on this factor
is therefore mostly a short position in high-volatility past losers, and its
risk is dominated by that leg. That is an exposure story, not a momentum story,
and it is exactly what the Week 5 beta/volatility neutralisation should test.

## 6. Persistence and turnover

| Metric | Value |
|---|---|
| Mean rank autocorrelation, 1 trading day | 0.987 |
| Mean rank autocorrelation, 20 trading days | 0.768 (range 0.27–0.92) |
| Mean turnover per 20-day rebalance | 0.895 |
| Traded notional per rebalance | 1.79 × NAV |

Day-to-day rank stability is very high, as expected for a 100-day compounded
window: the factor is a slow-moving object and there is no case for rebalancing
more often than the forecast horizon. But 20-day rank autocorrelation of 0.77
still implies that roughly 90% of the decile-1/decile-10 book turns over each
month, because decile membership at the tails is much less persistent than the
average rank. The autocorrelation itself is unstable — it falls to 0.27 in
stressed periods, exactly when the book is most expensive to trade.

## 7. Gross and net performance

226 non-overlapping 20-day periods, 2006–2023.

| Cost | Ann. return | Ann. vol | Sharpe | Hit rate | Max drawdown |
|---|---|---|---|---|---|
| Gross | 4.26% | 22.6% | **0.188** | 58.4% | −69.5% |
| 1 bp | 4.03% | 22.6% | 0.178 | 58.4% | −69.7% |
| 5 bp | 3.13% | 22.6% | 0.138 | 58.4% | −70.6% |
| 10 bp | 2.00% | 22.6% | 0.088 | 57.1% | −71.6% |
| 20 bp | −0.26% | 22.6% | **−0.011** | 55.3% | −73.6% |

With turnover of 0.895 and traded notional of 1.79× per rebalance, each basis
point of cost removes about 2.25 bp of monthly return, or ~28 bp annualised.
**Breakeven cost is ≈19 bp per unit of traded notional.** Even at 1 bp the gross
Sharpe of 0.19 is not investable on its own.

### The result is dominated by one episode

| Sub-period | Gross Sharpe | Net Sharpe @10bp | Ann. return (gross) | Max DD |
|---|---|---|---|---|
| 2006–2009 | −0.31 | −0.39 | −10.1% | −67.3% |
| 2010–2023 | 0.45 | 0.33 | 8.4% | −36.9% |
| 2015–2023 | 0.39 | 0.29 | 8.5% | −36.9% |

The three worst periods are −41.6% (ending 2009-04-07), −26.4% (2009-03-10) and
−24.5% (2022-06-14). The first two are the well-documented 2009 momentum crash,
and together they account for essentially the entire drawdown: the cumulative
curve falls from ~1.3 to ~0.55 in a few months of 2009 and never recovers to its
2008 high. Post-2009 the strategy grinds upward at a gross Sharpe of ~0.45,
which drops to ~0.33 at 10 bp.

Reporting "2010–2023 Sharpe 0.45" would be a start-date choice made after
seeing the crash, so the full-sample number is the honest headline. The correct
statement is that the factor's full-sample record is a coin flip whose tail risk
is severe and concentrated.

## 8. Interpretation

1. **The classical momentum premium does not show up here at a 20-day horizon in
   a liquid, price-≥$5, $5m-dollar-volume universe over 2006–2023.** Mean rank
   IC is zero. This is consistent with the published post-2000s decay of
   momentum in large-cap U.S. equities, but the point of the exercise is that
   the pipeline reproduces the null rather than manufacturing a premium.
2. **The small positive Pearson IC comes from the left tail, not the right.** The
   decile hump says extreme past losers underperform; past winners are
   unremarkable. Whatever is there looks like a distress/volatility exposure.
3. **Slow signal, fast book.** High rank autocorrelation coexists with ~90%
   monthly turnover because tail-decile membership is fragile. Persistence at the
   mean does not imply low turnover at the extremes; that distinction matters when
   the same diagnostic is used to argue a factor is cheap to trade.
4. **Cost sensitivity is decisive well before model complexity is.** The factor
   dies between 10 and 20 bp. Nothing in Weeks 4–5 can rescue a signal whose
   gross Sharpe is 0.19.

## 9. Limitations

- **Delisting returns.** As documented in Week 1, the export has no separate
  delisting-return field, so targets spanning a stock's exit are censored rather
  than filled with a delisting outcome. This biases *against* observing the
  worst outcomes for the short leg — the loser decile is where delistings
  cluster — so the true decile-1 return is plausibly lower and the true
  long-short return plausibly higher than reported here. The direction of the
  bias is known; the magnitude is not.
- **Non-overlapping rebalancing** uses one of 20 possible date offsets. It is
  the simplest defensible convention and it keeps the turnover and cost
  arithmetic honest, but it discards 95% of the available start dates. The daily
  IC series uses all of them, and the two tell the same story.
- **No neutralisation.** These are raw-factor results. Sector, beta and size
  exposures are unmeasured; §5 suggests they matter.
- **Equal weighting inside deciles** loads on the smallest eligible names, which
  are the most expensive to trade. Realised costs would exceed the flat per-unit
  assumption used here.
- **One factor, one window.** No window search was performed and none should be
  performed on this sample without an explicit multiple-testing accounting.

## 10. Decision

**Keep the factor in the six-signal set; do not treat it as a standalone
strategy.** It stays because the MVP's research question is which of six
interpretable signals survive costs, and a documented null is a valid answer to
that question. It may still contribute in a multi-factor model through
interactions or as a control even with zero marginal IC.

No change to the factor definition. The window is not re-tuned in response to
this result — that would be exactly the researcher-degrees-of-freedom problem
§15 of the plan warns about.

**Next:** apply this identical template to short-term reversal, realised
volatility, volume surprise, residual momentum and drawdown. Only `FACTOR_SQL`
and `FACTOR_SIGN` in `src/features/factors.py` change; the evaluation is
unchanged, so all six factors are measured the same way.
