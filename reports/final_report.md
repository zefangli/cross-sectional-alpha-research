# Cross-Sectional Alpha Research: Consolidated Report

**Do six interpretable price and volume signals forecast 20-trading-day
cross-sectional equity returns well enough to trade after costs?**

CRSP daily equities, 2005-2025. 2024-2025 sealed from the outset and opened
exactly once. Research period 2026-08-25 to 2026-09-11. All code, logs and
artefacts in this repository.

---

## 1. The claim, at the width the evidence carries

> A frozen five-factor specification produced positive, nominally significant
> returns during its single 2024-2025 held-out outcome test, including after the
> modelled transaction costs.

Gross Sharpe 1.52 (Newey-West `t` = 2.76), net Sharpe 1.22 at 10 bp, realised
market beta -0.065, maximum drawdown 4.1%, over 501 trading days.

**This does not establish durable or deployable alpha.** The test covers two
years. The cost model omits borrow cost, market impact, short availability and
capacity. The specification was the best of twenty admissible candidates. And
the five weeks of research preceding it found essentially nothing
distinguishable from zero.

The project's real output is a research process whose negative results are
credible. Most of what follows is nulls.

---

## 2. Design

Three commitments, made in Week 0 and kept:

1. **A sealed final test.** 2024-2025 was never evaluated until a single
   pre-registered run. The seal was enforced in code, not by intention.
2. **Pre-registration.** Every experiment was logged in `experiments.csv` with a
   hypothesis, a metric and a decision rule. Week 5's specifications, including
   the success criteria and the final selection rule, were written before any
   Week 5 result existed.
3. **Leakage control as a tested property, not an assumption.** Every factor and
   exposure is verified by a test that perturbs every input at or after date *t*
   and asserts the value at *t* is unchanged.

The target is the forward 20-trading-day total return. Targets therefore overlap
by 20 days, so **every t-statistic in this report is Newey-West at 20 lags**.

---

## 3. Data and universe

21,104,236 daily rows, 2005-01-03 to 2025-12-31. The eligible universe requires
price >= $5, twenty prior days of dollar volume averaging >= $5m, and >= 252
prior valid returns, all evaluated point-in-time: 8,399,139 eligible rows, of
which 8,319,133 carry all six factors. Roughly 1,660 names per date.

Three data facts materially changed the implementation:

- **Security classification must come from dated interval records, not header
  flags.** `SecurityActiveFlg` describes a security's *current* state and using
  it would have imposed survivorship. The same trap recurred in Week 5's sector
  field: for PERMNOs whose SIC code changed, the header row matches the *first*
  interval more often (7,420) than the last (3,137).
- **`price`, `volume` and `shares_outstanding` are as-traded in this export
  while `ret` is split-adjusted**, verified on Apple's 2014 seven-for-one split.
  So volume surprise uses turnover (split-invariant) and drawdown uses a
  cumulative total-return index rather than price. Both have split-invariance
  tests.
- **This export carries no delisting-return field.** Incomplete post-exit target
  windows are censored. Survivorship is reduced, not eliminated. This limitation
  stands over every result in this report.

---

## 4. Factors and timing

| factor | definition | sign |
|---|---|---|
| `mom_120_20` | return over t-120..t-21, skipping the recent month | + |
| `rev_5` | negated 5-day return | + |
| `rvol_20` | 20-day realised volatility | - |
| `vs_20` | log turnover against its 20-day mean | + |
| `rmom_120_20` | sum of market-model residuals over t-120..t-21 | + |
| `dd_252` | drawdown from the trailing one-year peak | + |

Residual momentum fits a single SQL expression because the sum of market-model
residuals has a closed form in window aggregates; a test checks it against an
explicit numpy OLS fit.

**Every factor is fully determined by the close of t-1.** Two originally were
not: `vs_20` and `dd_252` used day-*t* information against a day-*t* target.
That is leakage-free -- no future data is read -- but it implies same-close
execution. Lagging them one day cost `vs_20` about a third of its significance
(Newey-West `t` 3.43 to 2.50) and left `dd_252` almost unchanged. The general
lesson: **the more of a signal sits in its most recent observation, the more of
it is an execution assumption rather than a forecast.**

---

## 5. Single factors: one survivor

Evaluated through 2023 only, with Bonferroni across six tests (critical
|t| ~ 2.64):

| factor | mean rank IC | NW t | verdict |
|---|---|---|---|
| `rvol_20` | -- | strongest | **survives Bonferroni** |
| `vs_20` | 0.0039 | 2.50 | does not survive |
| `rev_5` | -- | -- | does not survive |
| `dd_252` | -- | 1.44 | insignificant |
| `mom_120_20` | -0.00002 | 0.00 | flat null |
| `rmom_120_20` | -- | -- | null, wrong sign |

No factor is viable at 20 bp. Five of six show **hump-shaped decile returns** --
the extreme bucket is not the best bucket -- so tail-decile books understate the
signals.

One estimator finding worth recording: a single-offset 20-day rebalance is an
unstable estimator. `rev_5` showed a negative gross Sharpe on offset 0 despite a
significantly positive IC, with a spread of -0.315 to +0.547 across the twenty
possible offsets. All portfolio statistics from Week 2 onward average over all
offsets, and Week 3 onward uses staggered daily cohorts instead.

---

## 6. Cross-factor structure: six signals, fewer bets

| pair | rank correlation | **portfolio-return correlation** |
|---|---|---|
| `rmom_120_20` / `mom_120_20` | 0.73 | **0.76** |
| `rvol_20` / `dd_252` | -0.48 | **0.87** |
| `mom_120_20` / `rvol_20` | -0.10 | **0.46** |

**Portfolio-return correlation is the informative measure.** Volatility and
drawdown rank stocks nearly oppositely yet their books correlate 0.87; momentum
and volatility look independent by rank yet their books correlate 0.46. Only
`rev_5` and `vs_20` are genuinely independent, and the equal composite barely
touches them.

The baseline book -- dollar-neutral, 1% position cap, 20 staggered daily
cohorts, daily-marked P&L -- returned a gross Sharpe of 0.121 over 2006-2023
with an 8.7 bp breakeven. A weighting ablation then **rejected my own earlier
claim** that rank-continuous weights would beat tail deciles: decile weighting
won 5 of 7 on gross Sharpe and 6 of 7 on turnover. The mechanism was right and
the conclusion backwards -- rank weights don't avoid the broken tail buckets,
they add the low-signal middle and its trading.

**Dollar-neutral is not beta-neutral.** Every book carried a persistent short
market position (composite beta -0.23, negative in every rolling 252-day
window), which is why Week 5 exists.

---

## 7. Models lose to the composite

OLS, Ridge and histogram gradient boosting over the six factor ranks, fitted
independently inside each of ten purged expanding walk-forward folds
(2014-2023), then run through the unchanged portfolio engine.

| book | gross SR | HAC t | net@10bp | breakeven |
|---|---|---|---|---|
| `composite` | 0.297 | 1.01 | **+0.163** | 22.2 bp |
| `composite__decile` | 0.297 | 0.99 | +0.155 | 20.9 bp |
| `gbm__decile` | 0.099 | 0.32 | -0.069 | 5.9 bp |
| `ridge` / `ols` | 0.085 / 0.084 | 0.26 | -0.165 / -0.167 | ~3.4 bp |

**Out-of-sample R-squared is negative for all three models**: against the
training-period mean, none has any point-prediction skill. The entire edge is
weak cross-sectional ordering (rank IC ~0.022, NW `t` ~8.8).

The mechanism of the loss: OLS earns 0.45% gross on a 0.70 mean gross book at
6.8x annual turnover; the composite earns 2.50% on a 0.90 book at 5.6x. **The
models trade more for less.** Their lower gross exposure is itself diagnostic --
a noisier signal self-cancels across the twenty live cohorts.

Two findings worth more than the ranking:

**A look-ahead bug, found in review and corrected.** The first design pre-ramped
each validation year's book on the twenty trading days before it -- exactly the
window in which the training rows' twenty-day targets are realised. A model
trained through the cutoff had already seen those returns. Removing it cut the
model books' gross Sharpe by 31-43% and the composite's by only 11%, because the
composite depends on no fitted model. That asymmetry is the mechanism confirming
itself.

**Ridge's penalty is unidentified under MSE tuning.** Inner-validation MSE falls
monotonically out to alpha = 1e10 for a total improvement of 0.005%, because on
a 20-day forward return MSE is almost entirely irreducible variance. Yet the
penalty materially changes the ranking: predictions at alpha 1e4 and 1e10
correlate only 0.86 by daily cross-sectional rank, because Ridge rotates
coefficients rather than scaling them -- momentum's loading flips sign. **MSE is
the wrong selection criterion for a cross-sectional ranking problem.** The
pre-registered grid was kept rather than retuned after seeing this.

---

## 8. Neutralisation fails its pre-declared test

Point-in-time sector (SIC division), rolling `beta_252` and `log_mcap`, all
determined at t-1, 100% coverage on the aligned panel. Scores were residualised
cross-sectionally per date and the books rerun.

The criterion, fixed in advance: **beta materially closer to zero AND net Sharpe
at 10 bp no worse.** Result: **7 of 8 books FAIL.**

Beta is not what fails -- every book sheds 75-98% of it. Net-of-cost Sharpe is
what fails, and the mechanism is the most useful finding of the week:

| composite | raw | neutralised | ratio |
|---|---|---|---|
| annualised volatility | 8.43% | 4.12% | **0.49** |
| annualised cost drag at 10 bp | 1.13% | 1.14% | **1.01** |
| annual turnover | 5.64x | 5.72x | 1.01 |
| net Sharpe at 10 bp | 0.163 | 0.081 | **0.49** |

**Neutralisation halves the volatility while the trading bill stays identical.**
A fixed cost charged against half the risk budget doubles its bite in Sharpe
terms. This cannot be levered away: scaling the book scales returns, turnover
and costs together, so net Sharpe is leverage-invariant.

Judged on gross Sharpe alone, OLS and Ridge nearly *tripled* and neutralisation
would have been recorded as a clean win. It was only visible because the
criterion was written in net terms in advance.

**Robustness.** Leave-one-out ablation found `rmom_120_20` and `vs_20` redundant
and `mom_120_20` and `rev_5` not, with every ablated book at HAC |t| <= 1.29 --
so nothing was dropped on that evidence alone. Regime and calendar slices
produced an apparent low-volatility tercile at `t` = 2.43 and a 2018 at 2.21;
both are the best of many ex-post slices of a series whose full-sample `t` is
1.0, the twenty-day overlap makes 832 days closer to 40 independent
observations, and the tercile boundaries used full-sample quantiles so the split
is not implementable. Neither is reported as a finding.

**The most fragile number in the study** is breakeven cost. Across four
pre-declared holding periods {5, 10, 20, 40} gross Sharpe barely moves
(0.297-0.383, every HAC `t` in 1.00-1.27) while breakeven swings **10.4 to 38.5
bp**, driven by turnover falling fivefold. Breakeven is a property of the
holding period at least as much as of the signal.

---

## 9. The lock

Rule, declared before any Week 5 result: **maximise net Sharpe at 10 bp subject
to realised market beta within 0.10 of zero**, applied mechanically to every
candidate book.

The first grid was incomplete -- it varied weighting and neutralisation but only
contained *raw* ablations, and since every raw ablation fails the beta
constraint, factor set could not genuinely compete. Adding the twelve
neutralised ablations took the grid to **40 candidates, 20 admissible**, and the
winner changed.

**Locked: `drop_rmom_120_20__neutral__decile`** -- five factors (`mom_120_20`,
`rev_5`, `rvol_20`, `vs_20`, `dd_252`), neutralised, decile weighted, 20-day
staggered cohorts, dollar-neutral, 1% cap. The dropped factor is the one the
ablation had already flagged as the redundant half of the momentum pair.

Completing the grid made the selection *statistically weaker*, not stronger: the
winner is the maximum of twenty correlated admissible estimates rather than
eight. The margin over the runner-up is 0.0103, and the runner-up has the higher
HAC `t` (1.97 against 1.65) -- the rule selects on net Sharpe, not significance,
exactly as pre-registered.

---

## 10. The sealed test

Opened once, at commit `084f5eb`, running the specification locked at `fbbe574`
unchanged. Formation 2024-01-02 to 2025-12-02; P&L 2024-01-03 to 2025-12-31; 501
trading days.

| metric | 2014-2023 (selection sample) | **2024-2025 (sealed)** |
|---|---|---|
| gross Sharpe | 0.534 | **1.522** |
| HAC t | 1.65 | **2.76** |
| net Sharpe at 10 bp | 0.238 | **1.215** |
| net Sharpe at 1 / 5 / 20 bp | -- | 1.491 / 1.368 / 0.909 |
| breakeven | 18.0 bp | 49.7 bp |
| realised market beta | -0.056 | **-0.065** |
| max drawdown | -17.8% | -4.1% |
| mean rank IC | -- | 0.0364 (HAC t 4.63) |

Profitable at every cost tier tested, and beta stayed inside the selection
rule's 0.10 constraint out of sample without being required to.

### What restrains the reading

- **Not significantly better than the selection sample.** The difference is
  +0.99 with a HAC-consistent standard error of 0.639, so `t` = 1.55.
- **The magnitude is loosely pinned.** The HAC 95% interval on the Sharpe is
  **[0.44, 2.60]** (`SE = SR/t` = 0.550, volatility treated as fixed). An iid
  approximation gives [-0.52, 3.56] as a sensitivity; it assumes an independence
  the staggered cohorts violate, so the HAC interval governs. Using 1.52 as a
  forward expectation is unsupported.
- **Selection is not corrected for.** Pre-registration makes this a valid single
  test; it does not make expected out-of-sample performance equal the
  selection-sample estimate. Selection normally biases that expectation
  *downward*, so the upside surprise is not explained by it.
- **Two adjacent positive years are consistency, not two experiments** (2024
  Sharpe 1.39, HAC `t` 1.73; 2025 Sharpe 1.65, `t` 2.22; neither preferred).
- **The dropped factor is still an exposure.** Mean `rmom_120_20` exposure is
  0.248 despite exclusion, because the retained five correlate with it. Dropping
  a factor removes it as an *input*, not as an *exposure*. The largest exposures
  remain `mom_120_20` (0.443) and `dd_252` (0.355) -- the Week 3 cluster, never
  fully defused.

---

### Figures

All in `reports/figures/`, generated by `src/reporting/final_figures.py` from the
daily series already on disk. No figure computes a new test.

| figure | shows |
|---|---|
| `01_cumulative_return.png` | Both periods as **two separate curves, each rebased to 1.0**, never chained. Chaining would render the selection sample and the sealed test as one continuous live track record, which is false: the left side is the data the book was chosen on. |
| `02_sharpe_vs_cost.png` | Sharpe against cost for both periods, breakevens marked at 18.0 and 49.7 bp, sealed Sharpe annotated with its HAC interval [0.44, 2.60] rather than as a point. |
| `03_rolling_beta.png` | Rolling 252-day beta within each period against the +/-0.10 band; the sealed line stays inside it. Windows never straddle the seal. |
| `04_factor_exposures.png` | Exposures by period, showing `rmom_120_20` at 0.248 despite exclusion from the inputs. |
| `05_candidate_grid.png` | All 40 candidates by net Sharpe and beta, admissibility band shaded, winner starred. The winner sits atop a dense cluster of near-identical admissible books -- the multiple-comparisons burden, drawn rather than asserted. |
| `06_drawdown.png` | Drawdown from each period's own running peak, same non-chaining convention. |

---

## 11. Limitations

- Two years of out-of-sample data; one country, one asset class, one twenty-year
  window.
- No borrow cost, market impact, short availability or capacity analysis. The 1%
  position cap never binds, so the book is untested at size.
- The delisting-return limitation of Section 3 stands over everything.
- Breakeven cost is horizon-fragile (Section 8).
- The sealed period is **outcome-sealed but was not literally untouched**:
  exposures are built over full panel history because a t-1 rolling beta needs
  it, and an early exposure audit summarised 2024-2025 *covariate* rows. No
  sealed-period return, target or performance figure was computed before the
  final run, and the winsorisation quantiles came from a query restricted to
  dates through 2023-11-30. The audit now ends at 2023-11-30. Disclosed rather
  than described as an untouched seal.

---

## 12. Governance and reproducibility

- **`experiments.csv`** -- every experiment with hypothesis, metric, result and
  decision. Week 5 rows were written before their results existed.
- **`reports/week5/locked_specification.json`** -- the frozen specification:
  factor names and signs, neutralisation controls, winsorisation quantiles,
  weighting, hold days, cap, candidate counts, runner-up and margin, and the
  commit it was generated from.
- **`reports/week6/sealed_run_started.json`** -- the atomic one-shot marker,
  created before any sealed data was opened and never removed.
- **The runner refuses** on a missing field, a factor sign disagreeing with the
  pre-registered sign, a recorded commit that is not an ancestor of HEAD, an
  uncommitted `src/` or lock file, or a runner whose content at the recorded
  commit differs from what is executing. Reaching the sealed period requires
  typing a literal opt-in string; no argument exits before any data is opened.
- **`python src/evaluation/week6_final.py replay`** re-runs the locked
  specification over 2014-2023 and asserts it reproduces the recorded figures to
  ~1e-15. This verifies the final result's machinery without the sealed data.
- 71 tests, seconds to run, synthetic data, no built panels required.

---

## 13. What would change the conclusion

More out-of-sample time, or the same protocol on a different market -- a genuine
replication rather than another look at the same data. **Not** more analysis of
2024-2025: anything further on those years is post-test by construction.

Before the word "deployable" could be used: borrow cost, a market-impact model,
short availability, and a capacity analysis.

The specification stays locked. This test is not repeatable on this data.
