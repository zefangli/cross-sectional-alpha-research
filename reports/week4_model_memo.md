# Week 4: Walk-forward model comparison

Date: 2026-09-10. Experiments: W4-001 .. W4-006.
Validation window: 2014-01-03 to 2023-12-29, ten fixed folds. 2024-2025 sealed.

> **Revision, 2026-09-10 (W4-005, W4-006).** The first version of this memo
> pre-ramped each fold's book on a 20-trading-day warm-up block before its
> validation year. That block was look-ahead contaminated and its portfolio
> numbers are withdrawn. Sections 4, 5, 6 and 10 below are the recomputed
> results. Section 3, the prediction metrics, is unaffected and unchanged.
> The correction moved every model book down by 31-43% of gross Sharpe and the
> composite by 11%; the conclusions hold and are stronger. Details in section 4a.

## 1. What was tested

Three models over the six factor ranks from Week 3, fitted independently inside
each of the ten walk-forward folds locked in `src/models/splits.py`:

| model | specification | tuning |
|---|---|---|
| `ols` | `LinearRegression` on the six ranks | none |
| `ridge` | `Ridge`, alpha by inner chronological split | 7-point grid, `logspace(-2, 4)` |
| `gbm` | `HistGradientBoostingRegressor` | none; hyperparameters pre-declared |

Gradient boosting uses scikit-learn's histogram booster rather than LightGBM.
LightGBM is not installed and was not added for one model; this is the same
histogram-boosting algorithm inside a dependency the project already has. The
substantive result does not rest on that choice.

No factor was manually reweighted. Each model learned its own weights inside
each training fold, and the equal-weighted composite it is measured against
uses the signs pre-registered in Week 0, not fitted ones.

## 2. Leakage controls

- Training rows are `aligned`, target not null, `date <= fold.train_end`, where
  `train_end` sits 21 trading days before the validation year begins. No fold
  trains on a return realised inside its own validation window.
- Predictions are generated for validation dates only. Cohorts are formed only
  on validation dates, and the whole 2014-2023 span is a single continuous
  backtest: a cohort formed in December under one fold's model runs off into
  January under the next fold's, which is how a live book behaves when the
  model is refitted annually. There is exactly one ramp-up, at the start of
  2014, identical for every book, and all eight books are compared on an
  identical 2,515-day index.
- All preprocessing lives inside an sklearn `Pipeline`, so the scaler
  structurally cannot see a validation row. The ridge alpha search runs on an
  inner chronological split of the training dates only, with its own 20-day
  purge.
- Nothing in this week reads a date after 2023-11-30 for cohort formation.
  Asserted before the predictions are written and again in the test suite.

Eight tests in `tests/test_week4.py` pin these properties, including the exact
fold boundary arithmetic and a named regression test for the warm-up bug: the
earliest predicted row must fall strictly after `train_end` plus 20 trading
days. 40 tests pass.

## 3. Prediction quality

Unaffected by the section 4a correction: these are scored on validation rows,
which were never part of the contaminated block. Pooled over 4,293,065 scored
validation rows per model:

| model | MSE | MAE | OOS R2 | Pearson IC | NW t | rank IC | NW t |
|---|---|---|---|---|---|---|---|
| `ols` | 0.016727 | 0.08525 | -0.00065 | 0.0124 | 5.29 | 0.0220 | 8.82 |
| `ridge` | 0.016726 | 0.08525 | -0.00065 | 0.0125 | 5.09 | 0.0221 | 8.59 |
| `gbm` | 0.016723 | 0.08521 | -0.00042 | 0.0268 | 10.03 | 0.0197 | 7.74 |

Out-of-sample R2 is negative for all three: against the training-period mean
target, none of the models has any point-prediction skill. The benchmark is the
training mean deliberately, not the validation mean, which would leak the
validation period's own average return into the denominator.

Whatever the models know is entirely in the cross-sectional ordering, where the
rank IC is small but genuinely significant at this sample size. `gbm` inverts
the usual pattern: the highest Pearson IC of the three and the lowest rank IC,
so it is fitting something in the tails that helps linear correlation without
improving the ordering that a portfolio actually trades.

Per-fold rank IC is negative in fold 3 (2016) and fold 7 (2020) for every
model. A shared regime effect, not a model defect.

## 4. Portfolio results

Every book is dollar-neutral, 1% position capped, 20 staggered daily cohorts,
daily-marked, run through the unchanged Week 3 engine over one continuous
2,515-day span. Sorted by net Sharpe at 10 bp.

`naive t` is `Sharpe x sqrt(years)`. `HAC t` is a Newey-West t-statistic on the
mean daily gross return at 20 lags, matching the holding period; the staggered
cohorts induce serial dependence, so the naive figure is only an approximation
and the HAC column is the one to read.

| book | gross SR | naive t | HAC t | net@10bp | breakeven bp | turnover/yr | beta | max DD |
|---|---|---|---|---|---|---|---|---|
| `composite` | +0.297 | 0.94 | **1.01** | +0.163 | 22.2 | 5.6 | -0.19 | -0.23 |
| `composite__decile` | +0.297 | 0.94 | **0.99** | +0.155 | 20.9 | 8.3 | -0.27 | -0.32 |
| `gbm__decile` | +0.099 | 0.31 | 0.32 | -0.069 | 5.9 | 8.1 | -0.22 | -0.31 |
| `gbm` | +0.098 | 0.31 | 0.32 | -0.086 | 5.4 | 5.5 | -0.14 | -0.22 |
| `ridge__decile` | +0.100 | 0.31 | 0.31 | -0.127 | 4.4 | 9.6 | -0.21 | -0.30 |
| `ols__decile` | +0.096 | 0.30 | 0.29 | -0.132 | 4.2 | 9.6 | -0.21 | -0.30 |
| `ridge` | +0.085 | 0.27 | 0.26 | -0.165 | 3.4 | 6.8 | -0.14 | -0.21 |
| `ols` | +0.084 | 0.26 | 0.26 | -0.167 | 3.3 | 6.8 | -0.14 | -0.21 |

**No fitted model beats the equal-weighted composite, on any metric, at any
cost tier.** Only the two composite books are net-positive at 10 bp; every
model book is negative there, and no model breakeven reaches 6 bp. Fitting
weights to the data lost to not fitting them, by a factor of three in gross
Sharpe.

The mechanism is visible in the components. `ols` earns an annualised 0.45%
gross on a 0.70 mean gross book while turning over 6.8x a year; the composite
earns 2.50% on a 0.90 book turning over 5.6x. The models trade more for less.
Their lower gross exposure is itself informative: a faster, noisier signal
self-cancels across the 20 live cohorts, so a larger share of each cohort's
intended book is netted away before it is ever held.

The naive and HAC t-statistics agree to within about 0.07 everywhere, so the
serial dependence induced by the staggered cohorts is real but mild, and the
inference verdict does not turn on which is used.

## 4a. The warm-up correction

The withdrawn design pre-ramped each fold's book on the 20 trading days before
its validation year, so that all 20 cohorts were live on the first scored day.
That block is exactly the window in which the training rows' 20-day forward
targets are realised: a model fit through `train_end` has already seen the
returns of `train_end + 1 .. train_end + 20`, and forming a cohort on those
dates trades on them. Ten folds meant ten contaminated stretches, each feeding
positions into the first 20 days of a validation year.

Replacing it with one continuous run also removed a second, unintended defect:
the per-fold design reset the cohort table at each of the nine internal year
boundaries, silently truncating the tail P&L of cohorts formed near a year end.

| book | withdrawn gross SR | corrected | change |
|---|---|---|---|
| `composite` | 0.333 | 0.297 | -11% |
| `composite__decile` | 0.335 | 0.297 | -11% |
| `gbm__decile` | 0.174 | 0.099 | -43% |
| `gbm` | 0.159 | 0.098 | -38% |
| `ridge__decile` | 0.144 | 0.100 | -31% |
| `ols__decile` | 0.140 | 0.096 | -32% |
| `ridge` | 0.137 | 0.085 | -38% |
| `ols` | 0.135 | 0.084 | -38% |

The asymmetry is the tell and it is what the mechanism predicts. The composite
depends on no fitted model, so its warm-up cohorts were never leaking; its 11%
move is the ramp window and the year-end tails alone. The model books lost a
third to nearly half, because for them the warm-up really was look-ahead. The
correction cost `gbm__decile` the only positive net-of-cost result any model
had produced, +0.008 at 10 bp, which is now -0.069.

Turnover and beta barely moved for any book, confirming the contamination sat
in returns rather than in portfolio mechanics.

The recomputed composite reproduces Week 3's own saved continuous daily series
exactly on all 2,515 dates except the 19 ramp days of January 2014, which is
independent confirmation that the new machinery is correct.

## 5. The comparison bar moved, and the old one was stale

Recomputing the Week 3 composite through identical machinery restricted to the
same validation span:

| | Week 3 memo, 2006-2023 | Recomputed, 2014-2023 |
|---|---|---|
| composite gross Sharpe, rank | 0.121 | **0.297** |
| composite gross Sharpe, decile | 0.147 | **0.297** |
| breakeven, rank | 8.7 bp | **22.2 bp** |
| breakeven, decile | 10.1 bp | **20.9 bp** |

This is a window effect, not a code change. The "beat 0.147 and 10.1 bp" target
recorded in PROGRESS.md was a 2006-2023 number and was never the right bar for
a 2014-2023 comparison.

## 6. What is actually significant

Almost nothing, and this is the week's real result.

| series | gross Sharpe | naive t | HAC t | years |
|---|---|---|---|---|
| composite, 2006-2013 | -0.112 | -0.31 | -0.31 | 7.9 |
| composite, 2014-2023 | +0.294 | +0.93 | +1.00 | 10.0 |
| composite, full | +0.121 | +0.51 | +0.52 | 17.9 |

Every book in section 4 has a HAC `|t| <= 1.01`. Not one of them, baseline
included, is distinguishable from zero at any conventional level. The models
are at 0.26 to 0.32.

The tempting story is that 2014-2023 was a better decade. The difference in
sub-period Sharpe is +0.406 with a standard error of about 0.476, so `t` is
0.85. There is no evidence the two sub-periods differ. Annual Sharpe estimates
on a series like this carry a standard error near 1.0 per year, and the
realised per-year values run from -1.60 to +2.76 -- exactly the dispersion
noise alone produces.

So the honest summary of Week 4 is not "the composite beat the models". It is
that a null was compared against three other nulls, and lost less badly. The
ranking in section 4 is a ranking of point estimates whose confidence intervals
all contain zero and nearly all of each other.

## 7. Ridge alpha is unidentified under MSE selection

The inner search chose alpha = 10,000 in all ten folds -- the maximum of the
pre-registered grid. Probing beyond it on fold 10, inner-validation MSE
decreases monotonically out to alpha = 1e10, for a total improvement of 0.005%
of MSE across twelve orders of magnitude. On a 20-day forward return, MSE is
almost entirely irreducible variance, so squared-error selection simply walks
toward the constant model.

That would be harmless if the shrinkage preserved the ordering. It does not.
Between alpha = 1e4 and alpha = 1e10 the mean daily cross-sectional Spearman
correlation of the predictions is 0.86, because ridge shrinks eigen-directions
at different rates and the coefficients rotate rather than scale: momentum's
loading goes from -17.4 bp to slightly positive as the collinear directions
collapse first.

**MSE is the wrong selection criterion for a cross-sectional ranking problem.**
It cannot identify the alpha, yet the alpha materially changes the portfolio.

The pre-registered grid is kept and Ridge is **not** retuned here. Choosing a
criterion after observing its effect is the researcher-degrees-of-freedom
problem the protocol exists to prevent. Rank-IC selection is instead carried
into Week 5 as a separate, declared, training-only robustness experiment, whose
result does not revise this week's headline either way.

## 8. What the models learned

Mean factor exposure of the rank-weighted books:

| factor | ols / ridge | gbm | composite |
|---|---|---|---|
| `mom_120_20` | 0.130 | 0.108 | 0.471 |
| `rev_5` | 0.035 | 0.021 | 0.018 |
| `rvol_20` | -0.240 | -0.327 | -0.290 |
| `vs_20` | 0.046 | 0.058 | 0.062 |
| `rmom_120_20` | 0.165 | 0.085 | 0.355 |
| `dd_252` | 0.231 | 0.250 | 0.392 |

The pre-registered expectation in PROGRESS.md was that a model would beat the
composite by weighting `rev_5` and `vs_20` -- the only two factors independent
of the momentum/volatility/drawdown cluster -- above equal weight. It partly
did: as a share of gross exposure the models tilt more toward those two than
the composite does, and `gbm` cuts `mom_120_20` and `rmom_120_20` while leaning
into `rvol_20`. It was not enough. Every model still loads mostly on the same
correlated cluster, which is where the variance is and therefore where a
squared-error objective points them.

One result the models produced unprompted is worth recording: the fitted OLS
coefficient on `mom_120_20` is negative, against the sign pre-registered in
Week 0, while the other five agree with their hypothesised signs. Week 2 found
momentum a null with the wrong sign by direct measurement. Nothing told the
model that.

## 9. Limitations

- Ten folds of one year each, one dataset, one universe. The dispersion in
  section 6 is the honest width of every estimate here.
- The models optimise squared error while the portfolio trades ranks. Section 7
  shows this is not a cosmetic mismatch.
- All books remain dollar-neutral but not beta-neutral, with beta between -0.14
  and -0.27. None of these Sharpes is a clean alpha.
- Overlapping 20-day targets are handled by Newey-West at 20 lags for both the
  IC series and the portfolio inference, but the training rows themselves are
  overlapping and are treated as independent by every model fitted here.
- GBM hyperparameters were declared once and never searched. A tuned GBM might
  do better; it would also need its own purged inner search and would inherit
  the criterion problem of section 7.
- The single 2014 ramp-up is kept rather than discarded. It is identical across
  all eight books, so it cannot favour one, but the first 19 days carry less
  than full gross exposure.

## 10. What Week 5 inherits

The bar for a same-period comparison is a gross Sharpe of 0.297 and a 22.2 bp
breakeven from the rank-weighted composite over 2014-2023 -- with the explicit
caveat that this number carries a HAC `t` of 1.01 and should be treated as an
estimate that could be zero.

Three concrete items follow from this week:

1. Neutralise beta, sector and size before comparing anything further. Section 8
   shows every model concentrating on the same correlated cluster Week 3 already
   identified, and section 4's betas show the books carry a persistent short
   market position. Until that exposure is removed it is not possible to say
   whether any of this is alpha.
2. Run rank-IC hyperparameter selection as a declared, training-only robustness
   experiment, per section 7.
3. Any future portfolio inference uses HAC t-statistics, not `Sharpe x
   sqrt(years)`.

2024-2025 remains sealed.
