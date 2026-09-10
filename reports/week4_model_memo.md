# Week 4: Walk-forward model comparison

Date: 2026-09-10. Experiments: W4-001 .. W4-004.
Validation window: 2014-01-02 to 2023-11-30, ten fixed folds. 2024-2025 sealed.

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
- Predictions are generated for a 20-trading-day warm-up block plus the
  validation year. The warm-up occupies the fold's own purge gap, is flagged
  `is_validation = False`, is never trained on, and exists so the 20 staggered
  daily cohorts are fully ramped on the first scored day. Measured gross
  exposure on the first scored day of each fold is 0.88-0.93 against a 0.906
  full-period median, so the ramp works.
- All preprocessing lives inside an sklearn `Pipeline`, so the scaler
  structurally cannot see a validation row. The ridge alpha search runs on an
  inner chronological split of the training dates only, with its own 20-day
  purge.
- Nothing in this week reads a date after 2023-11-30. Asserted before the
  predictions are written and again in the test suite.

Seven tests in `tests/test_week4.py` pin these properties, including the exact
fold boundary arithmetic (`validation_start - train_end == 21` trading days,
warm-up starting the very next day) and a check that corrupting the target
inside the purge gap leaves the chosen alpha unchanged. 39 tests pass.

## 3. Prediction quality

Pooled over 4,293,065 scored validation rows per model:

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
daily-marked, run through the unchanged Week 3 engine. Sorted by net Sharpe at
10 bp. `t` is the t-statistic of the gross Sharpe against zero over the 9.9-year
window.

| book | gross SR | t | net@10bp | breakeven bp | turnover/yr | beta | max DD |
|---|---|---|---|---|---|---|---|
| `composite` | +0.333 | 1.05 | +0.200 | 25.0 | 5.6 | -0.19 | -0.23 |
| `composite__decile` | +0.335 | 1.06 | +0.193 | 23.6 | 8.3 | -0.27 | -0.32 |
| `gbm__decile` | +0.174 | 0.55 | +0.008 | 10.5 | 8.1 | -0.22 | -0.28 |
| `gbm` | +0.159 | 0.50 | -0.022 | 8.8 | 5.4 | -0.14 | -0.20 |
| `ridge__decile` | +0.144 | 0.45 | -0.083 | 6.4 | 9.6 | -0.21 | -0.29 |
| `ols__decile` | +0.140 | 0.44 | -0.087 | 6.2 | 9.6 | -0.21 | -0.29 |
| `ridge` | +0.137 | 0.43 | -0.112 | 5.5 | 6.8 | -0.14 | -0.20 |
| `ols` | +0.135 | 0.43 | -0.114 | 5.4 | 6.8 | -0.14 | -0.20 |

**No fitted model beats the equal-weighted composite, on any metric, at any
cost tier.** The best model book clears 10 bp by 0.008 of Sharpe; OLS and Ridge
are net-negative there. Fitting weights to the data lost to not fitting them.

The mechanism is visible in the components. `ols` earns an annualised 0.74%
gross on a 0.70 mean gross book while turning over 6.8x a year; the composite
earns 2.81% on a 0.90 book turning over 5.6x. The models trade more for less.
Their lower gross exposure is itself informative: a faster, noisier signal
self-cancels across the 20 live cohorts, so a larger share of each cohort's
intended book is netted away before it is ever held.

## 5. The comparison bar moved, and the old one was stale

Recomputing the Week 3 composite through identical machinery restricted to the
same 2014-2023 validation dates:

| | Week 3 memo, 2006-2023 | Recomputed, 2014-2023 |
|---|---|---|
| composite gross Sharpe, rank | 0.121 | **0.333** |
| composite gross Sharpe, decile | 0.147 | **0.335** |
| breakeven, rank | 8.7 bp | **25.0 bp** |
| breakeven, decile | 10.1 bp | **23.6 bp** |

The recomputation reproduces Week 3's own saved daily series to 1e-16 on the
overlapping dates, so this is a window effect, not a code change. The
"beat 0.147 and 10.1 bp" target recorded in PROGRESS.md was a 2006-2023 number
and was never the right bar for a 2014-2023 comparison.

## 6. What is actually significant

Almost nothing, and this is the week's real result.

| series | gross Sharpe | t | years |
|---|---|---|---|
| composite, 2006-2013 | -0.108 | -0.30 | 7.9 |
| composite, 2014-2023 | +0.333 | +1.05 | 9.9 |
| composite, full | +0.121 | +0.51 | 17.9 |

Every book in the table in section 4 has `|t| <= 1.06`. Not one of them,
baseline included, is distinguishable from zero at any conventional level.

The tempting story is that 2014-2023 was a better decade. The difference in
sub-period Sharpe is +0.441 with a standard error of about 0.477, so `t` is
0.92. There is no evidence the two sub-periods differ. Annual Sharpe estimates
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

The pre-registered grid is kept for the headline rather than retuned after
seeing this, since choosing a criterion after observing its effect is precisely
the researcher-degrees-of-freedom problem the protocol exists to prevent. Week 5
should select on rank IC inside the training fold instead, declared in advance.

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
- Overlapping 20-day targets are handled by Newey-West at 20 lags for the IC
  series, but the training rows themselves are overlapping and are treated as
  independent by every model fitted here.
- GBM hyperparameters were declared once and never searched. A tuned GBM might
  do better; it would also need its own purged inner search and would inherit
  the criterion problem of section 7.

## 10. What Week 5 inherits

The bar for a same-period comparison is a gross Sharpe of 0.333 and a 25 bp
breakeven from the rank-weighted composite over 2014-2023 -- with the explicit
caveat that this number carries `t = 1.05` and should be treated as an estimate
that could be zero.

Two concrete items follow from this week:

1. Select model hyperparameters on rank IC, not MSE, declared before running.
2. Neutralise beta, sector and size before comparing anything further. Section 8
   shows every model concentrating on the same correlated cluster Week 3 already
   identified, and section 4's betas show the books carry a persistent short
   market position. Until that exposure is removed it is not possible to say
   whether any of this is alpha.

2024-2025 remains sealed.
