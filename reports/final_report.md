# Cross-Sectional Alpha Research: Consolidated Report

**Do six interpretable price and volume signals forecast 20-trading-day
cross-sectional equity returns well enough to trade after costs?**

CRSP daily equities, 2005-2025. 2024-2025 sealed from the outset and opened
exactly once. All code, logs and artefacts in this repository.

---

## 1. The claim, at the width the evidence carries

> A frozen five-factor specification produced positive, nominally significant
> returns during its single 2024-2025 held-out outcome test, including after the
> modelled transaction costs.

Gross Sharpe 1.43 (Newey-West `t` = 2.71), net Sharpe 1.06 at 10 bp (`t` =
2.01), realised market beta -0.063, maximum drawdown 3.6%, over 501 trading
days.

**These figures are a post-correction recomputation of the unchanged locked
specification over the already-seen 2024-2025 period, not a second sealed
test.** The seal was opened once, under the pipeline as it then stood; the
one-shot run's own numbers are preserved in `reports/week6/` and
`reports/week6_final_memo.md`. Nothing about the specification, the period or
the selection rule changed — only defects in the engine and panels beneath
them — but a recomputation on seen data is weaker evidence than the original
one-shot test, and is reported as such throughout. The defects, their
reproductions and the corrected recomputation are recorded in
`reports/project_*_review_*.md`, `reports/review_round*/` and
`reports/post_fix/`; they are not re-narrated here.

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

22,324,891 daily rows, 2005-01-03 to 2025-12-31. The eligible universe requires
price >= $5, twenty prior days of dollar volume averaging >= $5m, and >= 252
prior valid returns, all evaluated point-in-time using the close of *t*-1 so the
cross-section is fully known before the close it trades at: 8,395,800 eligible
rows, the large majority carrying all six factors. Roughly 1,660 names per date.

Three data facts materially shaped the implementation:

- **Security classification comes from dated interval records, not header
  flags.** `SecurityActiveFlg` describes a security's *current* state, and using
  it would impose survivorship. The same trap recurs in the sector field used
  for neutralisation: for PERMNOs whose SIC code changed, the header row matches
  the *first* interval more often (7,420) than the last (3,137), so sector is
  looked up as of the trade date from the interval table.
- **`price`, `volume` and `shares_outstanding` are as-traded in this export
  while `ret` is split-adjusted**, verified on Apple's 2014 seven-for-one split.
  So volume surprise uses turnover (split-invariant) and drawdown uses a
  cumulative total-return index rather than price. Both have split-invariance
  tests.
- **Delisting returns are present in CIZ format as a distinct row type.** A
  delisting return is a `DlyRet` row flagged `DlyDelFlg = 'Y'`, dated the trading
  day after the last trade and carrying placeholder classifications
  (`SecurityType = 'N/A'`, price 0) that fail an ordinary identity screen. There
  are 11,824 such rows, 11,445 with a return. The cleaner keeps one such row per
  delisted PERMNO (6,330 rows) rather than filtering it out with the other
  identity screens, the panel marks it like any other return, and a name is
  **settled to cash the day after its event**: a single correctly-sized exit
  trade (the drifted post-event value moving to zero), no further equity
  exposure, no further missing-return flagging for that name. A delisting inside
  a target window still leaves the complete 20-day label NULL while the
  position is marked on its observed window. Survivorship is reduced, not
  eliminated: 0.0007% of NAV a day, on average, is still in names whose rows end
  with no event return at all.

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

**Every factor is fully determined by the close of t-1.** `vs_20` and `dd_252`
are the two signals with the most weight on their most recent observation, and
both are computed one day lagged rather than off the same close they are
evaluated against -- same-close information is not future information, but it
does imply an execution assumption the lag avoids. Lagging costs `vs_20` real
significance (Newey-West `t` 2.73 after lagging and correcting a downstream
ranking bug) and leaves `dd_252` almost unchanged. The general lesson: **the
more of a signal sits in its most recent observation, the more of it is an
execution assumption rather than a forecast.**

---

## 5. Single factors: one survivor

Evaluated through 2023 only, with Bonferroni across six tests (critical
|t| ~ 2.64):

| factor | mean rank IC | NW t | verdict |
|---|---|---|---|
| `rvol_20` | -0.0286 | -2.85 | **survives Bonferroni** |
| `vs_20` | 0.0043 | 2.73 | survives |
| `rev_5` | 0.0074 | 2.04 | does not survive |
| `dd_252` | 0.0153 | 1.42 | insignificant |
| `mom_120_20` | -0.0002 | -0.02 | flat null |
| `rmom_120_20` | -0.0036 | -0.65 | null, wrong sign |

No factor is viable at 20 bp. Five of six show **hump-shaped decile returns** --
the extreme bucket is not the best bucket -- so tail-decile books understate the
signals.

One estimator finding worth recording: a single-offset 20-day rebalance is an
unstable estimator. `rev_5` showed a negative gross Sharpe on offset 0 despite a
significantly positive IC, with a spread of -0.32 to +0.54 across the twenty
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

The equal-weighted, dollar-neutral, 1%-cap, 20-staggered-cohort composite book
returned a gross Sharpe of 0.109 over 2006-2023, breakeven around 6.7 bp. A
weighting ablation across the six single factors plus the composite **rejected
an earlier expectation** that rank-continuous weights would beat tail deciles:
decile weighting won on gross Sharpe in 6 of 7 books (all but `rev_5`), at the
cost of higher turnover in every one of the 7. Decile weighting is retained
regardless as the Week 4 baseline because it was the pre-registered choice, not
because it dominates.

**Dollar-neutral is not beta-neutral.** Every book carried a persistent short
market position (composite beta around -0.19 to -0.27 depending on weighting,
negative in every rolling 252-day window), which is why Week 5 exists.

---

## 7. Models lose to the composite

OLS, Ridge and histogram gradient boosting over the six factor ranks, fitted
independently inside each of ten purged expanding walk-forward folds
(2014-2023), then run through the unchanged portfolio engine.

| book | gross SR | HAC t | net@10bp | breakeven |
|---|---|---|---|---|
| `composite` | 0.281 | 0.96 | **+0.126** | 18.1 bp |
| `composite__decile` | 0.286 | 0.96 | +0.115 | 16.7 bp |
| `gbm__decile` | 0.294 | 0.99 | -0.042 | 8.7 bp |
| `ridge` / `ols` | 0.013 / 0.012 | 0.04 | -0.168 / -0.168 | ~0.7 bp |

**Out-of-sample R-squared is negative for OLS and Ridge (about -0.0002) and
barely positive for GBM (+0.0003):** against the training-period mean, none has
meaningful point-prediction skill. The entire edge is weak cross-sectional
ordering -- mean rank IC around 0.022 for OLS and Ridge, 0.012 for GBM, with
Newey-West `t` of **2.0 (OLS/Ridge) and 2.3 (GBM)** once the daily IC series is
correctly date-ordered before the statistic is computed. `gbm__decile` edges the
composite on gross Sharpe (both HAC `t` near 1.0) and still loses net of costs.

The mechanism of the loss: OLS earns a 0.09% gross annualised return on a 0.83
mean-gross-exposure book at 6.5x annual turnover; the composite earns 2.32% on
a 0.90 book at 6.4x -- similar trading for a small fraction of the return. The
models' lower gross exposure is itself diagnostic -- a noisier signal
self-cancels across the twenty live cohorts.

Two findings worth more than the ranking:

**A look-ahead bug in the original walk-forward design.** The first design
pre-ramped each validation year's book on the twenty trading days before it --
exactly the window in which the training rows' twenty-day targets are realised.
A model trained through the cutoff had already seen those returns. Removing it
cut the model books' gross Sharpe by 31-43% and the composite's by only 11%,
because the composite depends on no fitted model. That asymmetry is the
mechanism confirming itself.

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
| annualised volatility | 8.28% | 4.12% | **0.50** |
| annualised cost drag at 10 bp | 1.28% | 1.29% | 1.01 |
| annual turnover | 6.41x | 6.43x | 1.00 |
| net Sharpe at 10 bp | 0.126 | 0.029 | **0.23** |

**Neutralisation roughly halves volatility while the trading bill stays flat --
but it also strips out most of the raw exposure's own edge, not just its beta,
so the fixed cost consumes the great majority of what is left.** Net Sharpe
falls to less than a quarter of its raw value, a far larger hit than volatility
alone would suggest. This cannot be levered away: scaling the book scales
returns, turnover and costs together, so net Sharpe is leverage-invariant.

Judged on gross Sharpe alone, OLS rises from 0.012 to 0.079 and Ridge from 0.013
to 0.080 -- more than sixfold -- and neutralisation would have been recorded as
a clean win. It was only visible as a failure because the criterion was written
in net terms in advance. The one passing book, `composite__decile`, improves
from 0.115 to 0.130 net while beta falls from -0.270 to -0.056.

**Robustness.** Leave-one-out ablation found `rmom_120_20` and `vs_20` redundant
and `mom_120_20` and `rev_5` not, with every ablated book at HAC |t| <= 1.25 --
so nothing was dropped on that evidence alone. Regime and calendar slices
produced an apparent low-volatility tercile at `t` = 2.42 and a 2018 at 2.33;
both are the best of many ex-post slices of a series whose full-sample `t` is
close to 1.0, the twenty-day overlap makes 832 days closer to 40 independent
observations, and the tercile boundaries used full-sample quantiles so the split
is not implementable. Neither is reported as a finding.

**The most fragile number in the study** is breakeven cost. Across four
pre-declared holding periods {5, 10, 20, 40} gross Sharpe barely moves
(0.28-0.36, every HAC `t` in 0.96-1.19) while breakeven swings **8.0 to 27.2
bp**, driven by turnover falling more than sixfold. Breakeven is a property of
the holding period at least as much as of the signal.

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
eight. The margin over the runner-up was narrow -- well inside the noise of a
single Sharpe estimate -- and more than one admissible candidate carries a
higher selection-sample HAC `t` than the winner: the rule selects on net
Sharpe, not significance, exactly as pre-registered.

**The corrected selection sample no longer ranks the locked book first.** The
lock was applied to the grid as computed under the pipeline of the time, and
that grid chose `drop_rmom_120_20__neutral__decile`. Recomputed under the
corrected engine, the same rule applied to the same grid would pick a
different book:

| candidate | net Sharpe at 10 bp |
|---|---:|
| `drop_vs_20__neutral__decile` | **0.157** |
| locked `drop_rmom_120_20__neutral__decile` | 0.136 |
| `drop_dd_252__neutral__decile` | 0.114 |

The lock is kept. It was a commitment made before the sealed period was
opened, and re-selecting on the corrected selection sample after seeing
2024-2025 would convert a pre-registered test into a fitted one -- the exact
failure the lock exists to prevent. The honest reading is that the winner was
never distinguishable from its neighbours: a 0.02 gap between the top two, on
estimates whose own HAC `t` values are 1.44 and 1.53, is noise. That the
ordering flipped under a bug fix is evidence of how little separated the
candidates, and is a further reason to treat the locked book as one draw from
a cluster rather than as an identified best.

---

## 10. The sealed test

Opened once, at commit `084f5eb`, running the specification locked at `fbbe574`
unchanged. Formation 2024-01-02 to 2025-12-02; P&L 2024-01-03 to 2025-12-31; 501
trading days.

| metric | 2014-2023 (selection sample) | **2024-2025 (sealed)** |
|---|---|---|
| gross Sharpe | 0.493 | **1.429** |
| HAC t | 1.53 | **2.71** |
| net Sharpe at 10 bp | 0.136 | **1.058** |
| net Sharpe at 1 / 5 / 20 bp | -- | 1.39 / 1.24 / 0.69 |
| breakeven | 13.8 bp | **38.5 bp** |
| realised market beta | -0.057 | **-0.063** |
| max drawdown | -17.1% | **-3.6%** |
| mean rank IC | -- | 0.031 (HAC t 3.95) |

Profitable at every cost tier tested, and beta stayed inside the selection
rule's 0.10 constraint out of sample without being required to.

### What restrains the reading

- **Not significantly better than the selection sample.** The difference is
  +0.94 with a HAC-consistent standard error of 0.618, so `t` = 1.51.
- **The magnitude is loosely pinned.** The HAC 95% interval on the Sharpe is
  **[0.40, 2.46]** (`SE = SR/t` = 0.527, volatility treated as fixed). An iid
  approximation gives a substantially wider interval as a sensitivity; it
  assumes an independence the staggered cohorts violate, so the HAC interval
  governs. Using 1.43 as a forward expectation is unsupported.
- **Selection is not corrected for.** Pre-registration makes this a valid single
  test; it does not make expected out-of-sample performance equal the
  selection-sample estimate. Selection normally biases that expectation
  *downward*, so the upside surprise is not explained by it.
- **Two adjacent positive years are consistency, not two experiments** (2024
  Sharpe 1.30, HAC `t` 1.73; 2025 Sharpe 1.55, `t` 2.16; neither preferred).
- **The dropped factor is still an exposure.** Mean `rmom_120_20` exposure is
  0.147 despite exclusion, because the retained five correlate with it.
  Dropping a factor removes it as an *input*, not as an *exposure*. The largest
  exposures remain `mom_120_20` (0.250) and `dd_252` (0.210) -- the Week 3
  cluster, never fully defused.

---

### Figures

All in `reports/post_fix/figures/`, generated by `src/reporting/final_figures.py`
from the daily series on disk. No figure computes a new test.

| figure | shows |
|---|---|
| `01_cumulative_return.png` | Both periods as **two separate curves, each rebased to 1.0**, never chained. Chaining would render the selection sample and the sealed test as one continuous live track record, which is false: the left side is the data the book was chosen on. |
| `02_sharpe_vs_cost.png` | Sharpe against cost for both periods, breakevens marked at 13.8 and 38.5 bp, sealed Sharpe annotated with its HAC interval [0.40, 2.46] rather than as a point. |
| `03_rolling_beta.png` | Rolling 252-day beta within each period against the +/-0.10 band; the sealed line stays inside it. Windows never straddle the seal. |
| `04_factor_exposures.png` | Exposures by period, showing `rmom_120_20` at 0.147 despite exclusion from the inputs. |
| `05_candidate_grid.png` | **Original selection record.** All 40 candidates by net Sharpe and beta, admissibility band shaded, winner starred. Both versions of this figure plot `reports/week5/candidates.csv` -- the grid as it stood when the lock was applied -- because that grid is what the selection rule actually saw; the corrected ranking is in Section 9, not here. The winner sits atop a dense cluster of near-identical admissible books -- the multiple-comparisons burden, drawn rather than asserted. |
| `06_drawdown.png` | Drawdown from each period's own running peak, same non-chaining convention. |

---

## 11. Limitations

- Two years of out-of-sample data; one country, one asset class, one twenty-year
  window.
- No borrow cost, market impact, short availability or capacity analysis. The 1%
  position cap never binds, so the book is untested at size.
- Delisting returns are paid where the export records them and a name is
  settled to cash the day after its event, but 0.0007% of NAV a day, on
  average (max 0.20%), is still in names whose rows end with no event return
  at all and accrue zero.
- One settlement in the locked 2024-2025 book rests on an unknown event
  payoff: a short position delisted with no recorded return, worth 0.056% of
  NAV. It is settled at an assumed zero return, not an observed one --
  disclosed and measured (`gross_unknown_event_payoff`), not netted into the
  figure above.
- Costs are charged on daily rebalancing to target weights, drift included,
  but still as a flat per-notional rate with no spread or impact model. The
  engine is a cost overlay on a target book, not a cash-reconciled execution
  simulator: NAV growth uses the gross return for every cost tier, costs are
  subtracted additively, and terminal liquidation shares the `traded` field
  with start-of-day trades. Settling a name to cash also means its freed
  capital is not redeployed, so mean gross exposure runs slightly under 1
  (0.945) rather than exactly at it.
- 0.002% of traded notional has no *return recorded* on the trade's execution
  date (`traded_missing_execution_return`) -- a return-availability proxy
  only. It does not check price, trading status, or settlement type, and a
  retained delisting row is exactly a case with a known return and no
  tradable price, so this number should not be read as untradeable notional or
  as fill verification. The ordinary halt/gap assumption -- a name can resume
  trading mid-hold -- is left open by design; only settlement after a
  *recorded* delisting event is handled specially.
- Breakeven cost is horizon-fragile (Section 8).
- The sealed period is **outcome-sealed but was not literally untouched**:
  exposures are built over full panel history because a t-1 rolling beta needs
  it, and an early exposure audit summarised 2024-2025 *covariate* rows only,
  ending at 2023-11-30. No sealed-period return, target or performance figure
  was computed before the final run, and the winsorisation quantiles came from
  a query restricted to dates through 2023-11-30. Disclosed rather than
  described as an untouched seal.

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
  uncommitted `src/` or lock file, a `src/` tree at HEAD that differs from the
  locked commit's, or a runner whose content at the recorded commit differs from
  what is executing. It does not authenticate the generated data panels or the
  package versions. Reaching the sealed period requires typing a literal opt-in
  string; no argument exits before any data is opened.
- **`python src/evaluation/week6_final.py replay [targets.json]`** re-runs the
  locked specification over 2014-2023 and asserts it reproduces the recorded
  figures to ~1e-15, using `reports/post_fix/week5/replay_targets.json`. This
  verifies the final result's machinery without the sealed data.
- The lock file is immutable by default; a rerun of the lock script writes
  `reselection.json` beside it.
- 101 tests, seconds to run, synthetic data, no built panels required, plus
  targeted synthetic reproductions of every settlement and diagnostic edge
  case in `reports/review_checks.py`.

---

## 13. What would change the conclusion

More out-of-sample time, or the same protocol on a different market -- a genuine
replication rather than another look at the same data. **Not** more analysis of
2024-2025: anything further on those years is post-test by construction.

Before the word "deployable" could be used: borrow cost, a market-impact model,
short availability, and a capacity analysis.

The specification stays locked. This test is not repeatable on this data.
