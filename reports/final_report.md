# Cross-Sectional Alpha Research: Consolidated Report

**Do six interpretable price and volume signals forecast 20-trading-day
cross-sectional equity returns well enough to trade after costs?**

CRSP daily equities, 2005-2025. 2024-2025 sealed from the outset and opened
exactly once. Research period 2026-08-25 to 2026-09-11; corrected after external
review on 2026-09-14 and again on 2026-09-15. All code, logs and artefacts in
this repository.

---

## 0. Corrections after review

After the sealed run, an external review
(`reports/project_review_2026-09-14.md`) found nine defects, a follow-up
review (`reports/project_followup_review_2026-09-15.md`) found five more,
including one the first round had got wrong, a third review
(`reports/project_round3_review_2026-09-15.md`) found two more in the fix
itself, and a fourth review (`reports/project_round4_review_2026-09-15.md`)
found two more narrow issues in *that* fix, plus an arithmetic error: 9+5+2+2
is 18, not the nineteen an earlier version of this section claimed. All
eighteen were fixed and the full pipeline was recomputed from the raw export
under the **unchanged** locked specification. The original sealed artefacts are untouched and remain the
one-shot record; the recomputation (`reports/post_fix/`) is a *correction audit*
of the same book on a period that had already been seen -- it cannot be a second
sealed test, and is not presented as one. The corrected figures are the ones to
quote.

| locked book, `drop_rmom_120_20__neutral__decile` | original record | **corrected audit** |
|---|---:|---:|
| 2024-2025 gross Sharpe (HAC `t`) | 1.522 (2.76) | **1.429 (2.71)** |
| 2024-2025 net Sharpe at 1 / 5 / 10 / 20 bp | 1.49 / 1.37 / 1.22 / 0.91 | **1.39 / 1.24 / 1.06 / 0.69** |
| 2024-2025 net Sharpe at 10 bp, HAC `t` | -- | **2.01** |
| 2024-2025 breakeven cost | 49.7 bp | **38.5 bp** |
| 2024-2025 annual turnover | 8.9x | **10.4x** |
| 2024-2025 realised market beta | -0.065 | **-0.063** |
| 2024-2025 max drawdown | -4.1% | **-3.6%** |
| 2024-2025 mean rank IC (HAC `t`) | 0.036 (4.63) | **0.031 (3.95)** |
| 2024-2025 HAC 95% interval on gross Sharpe | [0.44, 2.60] | **[0.40, 2.46]** |
| 2014-2023 gross Sharpe (HAC `t`) | 0.534 (1.65) | **0.493 (1.53)** |
| 2014-2023 net Sharpe at 10 bp | 0.238 | **0.136** |
| 2014-2023 breakeven cost | 18.0 bp | **13.8 bp** |
| sealed-minus-selection Sharpe, `t` | 1.55 | **1.51** |

What each defect was, and what it did:

1. **Turnover ignored price drift.** The engine compared today's target
   weights with yesterday's *targets*; restoring targets after a price move is
   a trade. Now charged against holdings drifted by the previous day's returns
   over the grown NAV. Turnover 8.9x to 10.4x; the largest single effect on net
   Sharpe.
2. **Week 2 formed portfolios only on stocks whose 20-day target was
   observable**, which is future information. Formation now uses every
   eligible stock with a signal; IC is a separate complete-pair diagnostic
   (target coverage 99.5%). Week 2 t-statistics move by about 0.1-0.2;
   `vs_20` now also survives Bonferroni (2.50 to 2.72).
3. **Missing returns were unresolved, undersized, and then misdiagnosed.** The
   cleaner applied entry screens as row filters, so a held name that changed
   issuer or conditional type vanished. It now keeps every common-share row.
   I then reported that the export carries no delisting returns at all. **That
   was wrong**, and the follow-up review caught it: the export holds 11,824
   rows flagged `DlyDelFlg = 'Y'`, 11,445 with a return, invisible to my scan
   because I conditioned it on the very identity screen that hides them -- event
   rows carry placeholder classifications (`SecurityType = 'N/A'`, price 0).
   The cleaner now keeps one such row per delisted PERMNO it already knows
   (6,330 rows), the panel marks it like any other return, and it can never be
   a formation row. The reviewer's worked example, PERMNO 80621 at -3.2161% on
   2014-02-03 while held long, is now paid. Ingesting the return was not
   enough on its own to fix the portfolio's accounting -- see defect 15.
4. **Week 4's Spearman IC ranked NULL targets** as if they were outcomes.
   Complete pairs only now, through one helper shared with Weeks 2 and 5.
5. **Competition ranks on ties, and a daily IC series never sorted by date
   before the Newey-West statistic.** Average ranks now, and an explicit sort.
   The models' rank-IC `t` falls from 7.7-8.8 to **2.0-2.3**; the mean IC
   barely moves. The earlier figure was an artefact of the unsorted series.
6. **Eligibility used the same-day close** (the $5 screen). It is now the
   screen at the close of t-1, so the cross-section is fully known before the
   close it trades at. Eligible rows 8,399,139 to 8,395,800.
7. **Normal reproduction overwrote the lock.** It is now immutable by default.
8. **The source-freeze check covered only the runner.** It now also compares
   the `src/` tree hash; the two historical commits share a tree, so the sealed
   run would have passed.
9. **Published numbers and replay targets were pre-fix.** Replay takes a
   targets file; both versions are documented in the README.

The follow-up review added five more, all fixed here:

10. **Week 2 erased known returns when the 20-day label was incomplete.** A
    holding whose data ended after a -50% day was marked flat for the whole
    period. Marking now uses `forward_return_20d_observed`, which compounds
    whatever the panel observed including the delisting return, while the
    complete label stays the requirement for IC and model targets. Names with
    no observation at all fall from about 3 per date to 0.006.
11. **Gap P&L was claimed correct in general.** It is not: the engine can book
    an entry or expiry trade in a name that has no observation that day, which
    assumes an execution the data do not establish. The claim is withdrawn and
    the assumption is now measured -- `traded_without_return` was **0.62% of all
    traded notional** in 2024-2025 at this point (superseded by defect 16).
12. **`--from-step` crashed the resume path**, because Week 2 read the runner's
    own flag off `sys.argv` as a factor name. The entry point takes explicit
    names now and rejects unknown ones.
13. **Corrected replay overwrote the historical replay files.** It writes next
    to its targets file instead; `reports/week6/` is verified byte-identical
    after a corrected replay.
14. **The stage-by-stage reproduction commands write to the historical report
    folders**, not the audit tree. Documented as the original-record workflow,
    with `run_post_fix_audit` as the way to rebuild the current version.

A third review checked this work and found the ingestion fix was incomplete
on the portfolio side, plus a second bug in the very diagnostic defect 11 had
just added:

15. **A delisted name kept its stale pre-event target weight and the engine
    tried to restore it.** Ingesting the event return (defect 3) fixed the P&L
    on the event day; it did nothing about the day after. The drift-aware
    trade math (defect 1) compares the *nominal* cohort weight against the
    *drifted* value of the holding, and nothing told it the nominal weight
    should now be zero -- after a total loss this reads as repurchasing a wiped-
    out security, which a synthetic -100% case showed directly. A name is now
    **settled to cash the day after its event**: a single correctly-sized exit
    trade (the drifted post-event value moving to zero), no further equity
    exposure, and no further missing-return flagging for that name. This is
    what defect 11's 0.51%-of-NAV figure actually was: **99.48% of it was
    retained equity in already-settled names**, not unresolved data. Settled,
    it falls to **0.0007% of NAV per day** (max 0.20%, was 2.19%).
16. **`traded_without_return` (defect 11) checked the wrong day.** The trade
    on row *d* executes at the close of *d*-1 (defect 1's own docstring says
    so); the diagnostic filtered on *d*'s return instead, which both misses a
    genuinely unobservable execution and flags an observable one depending on
    which side of a gap the missing row falls -- two synthetic entry cases
    showed both errors directly. Fixed to check *d*-1 (computed over every
    calendar day a name is tracked, so an entry trade still checks its true
    predecessor), and combined with defect 15's settlement fix, this fell from
    0.62% to 0.002% of traded notional at this point (renamed and re-scoped by
    defect 18 below).

A fourth review checked the settlement fix itself and found two more narrow
issues, both about what is disclosed rather than what is computed:

17. **Settlement treated an unknown event payoff as a verified one.** `settled`
    (defect 15) settles a name to cash the day after *any* delisting row,
    whether or not that row's own return is known. When it is NULL, the
    standing missing-return policy already accrues 0 and drifts the position
    at 0 -- so the exit the next day converts it to cash at its full pre-event
    value, a disclosed zero-return imputation, not an observed payoff. A
    synthetic +50%-NAV holding with a NULL event return confirmed the policy
    directly. This is real in the locked 2024-2025 book: PERMNO 16795, a short
    position, delisted on 2024-10-28 with no recorded return, an event-date
    exposure of **0.056% of NAV**. The no-repurchase rule stays exactly as is;
    the assumption is now measured separately as `gross_unknown_event_payoff`
    and `names_settled_unknown_payoff` rather than disappearing into ordinary
    settlement.
18. **The 0.002% figure (defect 16) is not a price or tradability audit.** It
    checks only whether CRSP recorded a *return* on the execution date --
    nothing about price, trading status, or whether a flow is a cash
    settlement rather than a market fill. A retained delisting row is exactly
    the case where a return is known and no tradable price exists, which is
    the opposite of what "no observed execution price" implied. Renamed
    `traded_without_return` to `traded_missing_execution_return` and withdrawn
    the untradeable-notional/fill-verification framing; it is a return-
    availability proxy, stated as such, and no more.

Ingesting a delisting return, then discovering that returns alone are not
settlement, then discovering that settlement itself needs known-versus-unknown
proceeds kept apart, is the shape of this whole correction process in
miniature: each fix closed one gap and exposed the next one behind it. The
four reviews together took the reported missing-return exposure from "the data
don't have it" (wrong) to "0.51% of NAV, a residual limitation" (an artefact
of unsettled equity) to "0.0007% of NAV, now genuinely small" (with one
disclosed 0.056%-of-NAV unknown-payoff exception, not netted into that figure).

The qualitative conclusions survive intact: one weak, nominally significant
out-of-sample result on a frozen specification; models lose to the composite
net of costs; neutralisation fails its pre-declared test in 7 of 8 books;
nothing before the sealed test was distinguishable from zero. What changed is
the size of the edge (smaller), the breakeven (lower) and, materially, how
significant the models' ordering skill ever was (much less).

The numbers in sections 1-10 are the **original record** unless marked
otherwise; the table above is the correction. Figures for both versions are in
`reports/figures/` (original) and `reports/post_fix/figures/` (corrected), drawn
by the same code.

---

## 1. The claim, at the width the evidence carries

> A frozen five-factor specification produced positive, nominally significant
> returns during its single 2024-2025 held-out outcome test, including after the
> modelled transaction costs.

On the corrected accounting: gross Sharpe 1.43 (Newey-West `t` = 2.71), net
Sharpe 1.06 at 10 bp (`t` = 2.01), realised market beta -0.063, maximum drawdown
3.6%, over 501 trading days. As originally recorded: 1.52, 1.22, -0.065, 4.1%.
The corrected figure is the one that has survived four rounds of external
review; the original is kept only as the record of what the one-shot run
produced.

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
- **Delisting returns are present and easy to miss.** In CIZ format a delisting
  return is a `DlyRet` row flagged `DlyDelFlg = 'Y'`, dated the trading day
  after the last trade and carrying placeholder classifications that fail every
  identity screen. There are 11,824 of them, 11,445 with a return; I first
  reported the opposite because my scan applied the same identity screen (see
  section 0, defect 3). They are now ingested, a name is settled to cash the
  day after its event rather than left as stale tradable equity (defect 15),
  and a delisting inside a target window still leaves the complete 20-day
  label NULL while the position is marked on its observed window.
  Survivorship is reduced, not eliminated: 0.0007% of NAV a day is still in
  names whose rows end with no event return at all.

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

| factor | mean rank IC | NW t (original / corrected) | verdict |
|---|---|---|---|
| `rvol_20` | -0.0286 | -2.85 / -2.85 | **survives Bonferroni** |
| `vs_20` | 0.0039 / 0.0043 | 2.50 / **2.73** | survives only after correction |
| `rev_5` | 0.0077 / 0.0074 | 2.12 / 2.04 | does not survive |
| `dd_252` | 0.0155 / 0.0153 | 1.44 / 1.42 | insignificant |
| `mom_120_20` | -0.00002 | 0.00 / -0.02 | flat null |
| `rmom_120_20` | -0.0036 | -0.63 / -0.65 | null, wrong sign |

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

**Out-of-sample R-squared is negative for all three models** (corrected: GBM
+0.0003, the others -0.0002): against the training-period mean, none has any
point-prediction skill. The entire edge is weak cross-sectional ordering (rank
IC ~0.022). The originally reported NW `t` of ~8.8 on that IC was an artefact
of an unsorted daily series; correctly ordered it is **2.0 (OLS/Ridge) and 2.3
(GBM)**. Corrected book figures: composite 0.281 gross / +0.125 net at 10 bp,
`gbm__decile` 0.315 gross / -0.022 net -- the model now edges the composite on
gross Sharpe (both HAC `t` about 1.0) and still loses net of costs.

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

(Corrected: net 0.125 to 0.028 for the rank-weighted composite; the 7-of-8
verdict is unchanged, and the one passing book, `composite__decile`, improves
from 0.115 to 0.130 net while beta falls from -0.270 to -0.056.)

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
trading days. Original record first; corrected audit (section 0) in the last
column.

| metric | 2014-2023 (selection sample) | **2024-2025 (sealed)** | 2024-2025 corrected |
|---|---|---|---|
| gross Sharpe | 0.534 (corrected 0.493) | **1.522** | 1.429 |
| HAC t | 1.65 (1.53) | **2.76** | 2.71 |
| net Sharpe at 10 bp | 0.238 (0.136) | **1.215** | 1.058 |
| net Sharpe at 1 / 5 / 20 bp | -- | 1.491 / 1.368 / 0.909 | 1.39 / 1.24 / 0.69 |
| breakeven | 18.0 bp (13.8) | 49.7 bp | 38.5 bp |
| realised market beta | -0.056 (-0.057) | **-0.065** | -0.063 |
| max drawdown | -17.8% (-17.1%) | -4.1% | -3.6% |
| mean rank IC | -- | 0.0364 (HAC t 4.63) | 0.0309 (3.95) |

Profitable at every cost tier tested, and beta stayed inside the selection
rule's 0.10 constraint out of sample without being required to.

### What restrains the reading

- **Not significantly better than the selection sample.** The difference is
  +0.99 with a HAC-consistent standard error of 0.639, so `t` = 1.55 (corrected:
  +0.94, SE 0.618, `t` = 1.51).
- **The magnitude is loosely pinned.** The HAC 95% interval on the Sharpe is
  **[0.44, 2.60]** (`SE = SR/t` = 0.550, volatility treated as fixed; corrected
  **[0.40, 2.46]**). An iid approximation gives [-0.52, 3.56] as a sensitivity;
  it assumes an independence the staggered cohorts violate, so the HAC interval
  governs. Using 1.5 as a forward expectation is unsupported.
- **Selection is not corrected for.** Pre-registration makes this a valid single
  test; it does not make expected out-of-sample performance equal the
  selection-sample estimate. Selection normally biases that expectation
  *downward*, so the upside surprise is not explained by it.
- **Two adjacent positive years are consistency, not two experiments** (2024
  Sharpe 1.39, HAC `t` 1.73; 2025 Sharpe 1.65, `t` 2.22; corrected 1.30 / 1.73
  and 1.55 / 2.16; neither preferred).
- **The dropped factor is still an exposure.** Mean `rmom_120_20` exposure is
  0.248 despite exclusion (corrected 0.147, on the fixed aligned-only ranks),
  because the retained five correlate with it. Dropping a factor removes it as
  an *input*, not as an *exposure*. The largest exposures remain `mom_120_20`
  (0.443; corrected 0.250) and `dd_252` (0.355; 0.210) -- the Week 3 cluster,
  never fully defused.

---

### Figures

All in `reports/figures/` (original record; embedded below), generated by
`src/reporting/final_figures.py` from the daily series already on disk, and
redrawn from the corrected series into `reports/post_fix/figures/` by the same
code with `--post-fix`. No figure computes a new test.

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
- Delisting returns are paid where the export records them and a name is
  settled to cash the day after its event, but 0.0007% of NAV a day, on
  average (max 0.20%), is still in names whose rows end with no event return
  at all and accrue zero.
- One settlement in the locked 2024-2025 book rests on an unknown event
  payoff: PERMNO 16795, a short position, delisted 2024-10-28 with no
  recorded return, 0.056% of NAV. It is settled at an assumed zero return, not
  an observed one -- disclosed and measured (`gross_unknown_event_payoff`),
  not netted into the figure above.
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
  *recorded* delisting event was fixed.
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
  uncommitted `src/` or lock file, a `src/` tree at HEAD that differs from the
  locked commit's, or a runner whose content at the recorded commit differs from
  what is executing. It does not authenticate the generated data panels or the
  package versions. Reaching the sealed period requires typing a literal opt-in
  string; no argument exits before any data is opened.
- **`python src/evaluation/week6_final.py replay [targets.json]`** re-runs the
  locked specification over 2014-2023 and asserts it reproduces the recorded
  figures to ~1e-15 -- the lock's own numbers on the original source, or
  `reports/post_fix/week5/replay_targets.json` on the corrected source. This
  verifies the final result's machinery without the sealed data.
- The lock file is immutable by default; a rerun of the lock script writes
  `reselection.json` beside it.
- 101 tests, seconds to run, synthetic data, no built panels required; the
  reviewer's four synthetic reproductions run as `reports/review_checks.py`.

---

## 13. What would change the conclusion

More out-of-sample time, or the same protocol on a different market -- a genuine
replication rather than another look at the same data. **Not** more analysis of
2024-2025: anything further on those years is post-test by construction.

Before the word "deployable" could be used: borrow cost, a market-impact model,
short availability, and a capacity analysis.

The specification stays locked. This test is not repeatable on this data.
