# Project review: correctness, quant CV value, and trading readiness

Reviewed 2026-09-14 against the current working tree, including the pre-existing
uncommitted corrections and `reports/post_fix/` artifacts.

## Assessment

This can support a quant research CV: it demonstrates point-in-time security
classification, interpretable features, purged chronological validation,
train-only preprocessing, cost sensitivity, and willingness to report negative
results. Its strongest contribution is the research and validation process.

The current evidence does not establish an implementable profitable strategy.
There are remaining accounting, data, and statistical defects. Fixing those is
more valuable than adding another model or expanding the parameter search.

## Verified findings

P1 means fix before relying on the affected performance claim. P2 means a
material correctness or reproducibility issue to address next. Effort estimates
below are planning estimates, not measured completion times.

### 1. P1: turnover compares target weights instead of actual holdings

**Location:** `src/portfolio/backtest.py:103`, `:116–117`;
`src/evaluation/factor_eval.py:85–91` has the same turnover approximation.

The daily engine calculates both today's and yesterday's weights from original
cohort allocations. Yesterday's weights never change with yesterday's returns.
It therefore reports zero trading when cohort targets remain constant, even
though restoring those weights after price moves requires trading. Conversely,
if the intended strategy holds shares unchanged for 20 days, its daily returns
must use the resulting changing holdings rather than constant cohort weights.

**Reproduced:** with weights +25% and -25%, a 10% return on the long leg and
zero on the short leg, the next day's traded fraction is reported as zero.
Restoring those target weights requires trading 2.439% of NAV before costs.
This is a concrete accounting inconsistency; the effect on the full strategy's
Sharpe has not been measured. Drift can increase or offset scheduled trades.

**Minimal fix:** choose and document one implementable convention. Keeping the
existing daily target weights is the smaller change: calculate pre-trade
holdings after returns, reconcile trades/cash/NAV, and charge costs on executed
notional, including final liquidation. A two-stock hand calculation should
reconcile the engine. This distinction is also explained in the
[skfolio backtesting documentation](https://skfolio.org/user_guide/backtesting_and_evaluation.html).

### 2. P1: the single-factor portfolios select on future target availability

**Location:** `src/evaluation/factor_eval.py:64` and `:143–154`.

`cross_section_query` removes rows with missing forward returns before ranking
and assigning deciles. `evaluate` constructs portfolio weights from that same
table. A stock disappearing during the next 20 days can therefore be excluded
from today's book using information unavailable at formation time. Complete
pairs are appropriate for a labeled IC diagnostic, but cannot define the
tradable formation universe.

**Reproduced:** changing only the highest-signal stock's future target to NULL
removes it from the formation cross-section. The stock's signal is unchanged.
This directly affects Week 2 factor portfolio claims. Weeks 3–6 correctly avoid
requiring the target for formation, so the defect should not be attributed to
their portfolio selection.

**Minimal fix:** form ranks and weights using contemporaneously available
information, then evaluate them separately. Reuse the corrected daily marking
engine for single-factor returns. Report target coverage and the difference
between complete-pair IC and the full investable universe.

### 3. P1: disappearing and ineligible holdings do not have resolved economic returns

**Location:** `src/data/clean_crsp.py:60`, `:108`;
`src/portfolio/backtest.py:111–117`, `:140–149`.

The cleaner filters the entire return history using the entry-universe rules,
including active trading status. These rules can remove records needed to mark
an already-held stock. The existing security audit records 1,160 suspended and
721 halted CORP/RW raw rows excluded by the active-status restriction; these are
raw counts, not distinct held positions. The book retains disappeared holdings
but assigns zero returns and eventually closes them at the carried valuation.
Counting the problem makes it visible; it does not establish an executable exit
or a correct delisting payoff. Effects can help or hurt a long-short portfolio.

**Measured from the existing corrected 2024–2025 daily artifact:** 3,701 held
position-days have missing returns, spread across 500 of 501 dates. Some may
carry tiny weights; counts alone cannot establish economic materiality. The
pre-fix artifact reported only three such position-days.

**Minimal fix:** separate entry eligibility from the return-marking universe;
preserve necessary inactive/event records. Investigate missing returns by
PERMNO, event, signed weight, and gross capital affected. Recover delisting
payments/returns or publish explicit sensitivity scenarios while they remain
unresolved. A temporary flat mark is different from assuming a permanent exit
at that value.

The manifest's inference from the absence of a separate delisting-return
column also needs refinement. CRSP CIZ identifies delisting-return observations
through `DlyDelFlg`; a separate legacy-style column is not the decisive check.
Audit the export query, event dates, and joins to determine whether those rows
were omitted. No conclusion about the raw export's full delisting coverage was
established in this review. See the
[CRSP CIZ guide](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-guide-flat-file-format-2-0/).

Also, 820 pre-2024 cleaned rows have P1–P9 return-duration flags. These represent
multi-trading-day returns, unlike D3 weekend returns. Their treatment across
gaps and changing positions needs an explicit check; do not simply discard
every return spanning multiple calendar days. See
[CRSP duration definitions](https://www.crsp.org/wp-content/uploads/appendix/FlagType_RD.html).

### 4. P1: Week 4 Spearman IC includes missing targets as ranked observations

**Location:** `src/evaluation/week4_models.py:113–125`.

The ranking query includes NULL targets. SQL assigns them a rank, so the later
correlation uses them as if they were valid outcomes. Pearson IC excludes NULL
pairs, creating an internal inconsistency between the two statistics.

**Reproduced:** predictions `[1, 2, 3, 0]` and targets `[1, 2, 3, NULL]` produce
Spearman IC **-0.20**, although the complete pairs have correlation **+1.00**.
The existing Week 5 implementation returns +1.00 on those same observations.
The research panel contains 19,126 missing targets among 4,293,065 aligned
rows in 2014-01-02 through 2023-11-30, so missing targets are not hypothetical.

**Minimal fix:** filter valid pairs before ranking. Reuse the average-rank
convention already implemented in `week5_neutral.daily_rank_ic`, then regenerate
Week 4 metrics in the correction-audit output tree.

### 5. P2: rank ties and unordered dates further invalidate some IC statistics

**Location:** `src/evaluation/week4_models.py:116–135`;
`src/evaluation/factor_eval.py:57–60`.

Week 4 and Week 2 use SQL competition ranks instead of average ranks, so their
reported Spearman correlations differ from standard Spearman when values tie.
Tree predictions and drawdown-at-zero values naturally contain ties. The prior
IC correction addressed Week 5, but not these sibling paths.

**Reproduced:** scores `[0, 0, 1, 2]` against `[1, 2, 3, 4]` return 0.946729262
instead of 0.948683298. The size depends on the tie pattern.

Separately, Week 4's daily aggregate has no `ORDER BY` and feeds directly into
Newey-West calculations. SQL grouping does not promise chronological output;
Pandas grouping by fold/model does not sort observations by date. A HAC
standard error depends on temporal adjacency, so this can alter significance
without changing the mean IC.

**Minimal fix:** average ranks on complete pairs, and explicitly sort by
model/fold/date before computing lagged statistics. Add a shuffled-input
invariance check and compare with the already-installed SciPy/Pandas rank
correlation implementation.

### 6. P2: the claimed t-1 execution rule omits same-day universe information

**Location:** `src/data/build_research_panel.py:43`;
`src/features/build_factor_panel.py:44–49`.

Factors and risk exposures are lagged, but eligibility uses the current day's
closing price. Eligibility determines the aligned cross-section and its ranks,
so the final weights are not necessarily known at t-1. The modeled first return
starts at the close of t, requiring weights that can actually be submitted for
that execution. Knowing the final close first and then trading at it is an
additional assumption, not the advertised full-day decision gap.

**Reproduced:** with identical prior history, changing only price(t) from $10
to $4.99 switches eligibility(t) from true to false. Existing factor-level
perturbation tests do not test the full eligibility-to-weight pipeline.

**Minimal fix:** use prior-day price and available universe information for
formation, or explicitly shift execution/returns after the complete decision
is known. Test invariance of final weights, not only raw factors.

### 7. P2: normal reproduction can overwrite the historical locked specification

**Location:** `README.md:114`; `src/evaluation/week5_lock.py:208`.

The documented reproduction commands include running `week5_lock.py`, which
unconditionally rewrites `reports/week5/locked_specification.json`. After the
existing corrections, this can change the book/metrics/commit that supposedly
identify the already-completed sealed experiment. The post-fix runner later
reads that same path. Preserving old sealed CSV files does not protect their
associated specification from this normal workflow.

**Minimal fix:** make an existing lock immutable by default, and write any
recomputed candidate ranking into a separate audit run directory. Do not
reselect the historical winner following inspection of 2024–2025.

### 8. P2: the source-freezing check does not freeze its imported research code

**Location:** `src/evaluation/week6_final.py:152–173`.

The frozen-runner check compares only `week6_final.py` with the locked commit.
A later committed change to the backtest, factors, or neutralisation code can
pass the ancestry check, clean-tree check, and identical-runner check while
executing a different strategy. This is a gap in the stated guarantee, not
evidence that the historical test was deliberately manipulated.

**Verified:** the checked git operations authenticate ancestry, working-tree
cleanliness, and this runner's contents only. No dependency-tree comparison is
performed. Generated factor/exposure panels and dependency versions are also
not authenticated against the original run.

**Minimal fix:** record/verify the relevant source-tree content and the hashes
of the specification and generated input artifacts. Pin the environment used
for publication. Keep the one-shot marker as an accident guard; describe the
reproducibility guarantees at the level actually enforced.

### 9. P2: public results and replay expectations remain on the pre-fix version

**Location:** `README.md:18`, `:167–181`; `reports/final_report.md:19`;
`src/evaluation/week6_final.py:455–466`.

The README/final report still lead with pre-fix results without pointing the
reader to the completed correction audit. Current corrected metrics do not
match the immutable original lock's replay targets.

| Metric | Original record | Existing correction audit |
|---|---:|---:|
| 2024–2025 gross Sharpe | 1.5216 | 1.4923 |
| 2024–2025 net Sharpe, 10 bp | 1.2151 | 1.1706 |
| 2024–2025 market beta | -0.0652 | -0.0625 |
| 2014–2023 locked-book gross Sharpe | 0.5337 | 0.4916 |
| 2014–2023 locked-book net Sharpe, 10 bp | 0.2379 | 0.1793 |

The corrected 2014–2023 metrics fail all three required original replay target
comparisons at the runner's configured tolerance. This was verified using
saved corrected results and the comparison rule, not by running the expensive
replay. The README's 71-test count is also outdated: 79 tests now pass.

**Minimal fix:** add a visible correction notice, a versioned results table,
and separate instructions for reproducing the original snapshot versus the
current audit. Preserve both histories; label corrected results as corrected
results, not a newly untouched test. Update the CV-facing report and figures
together after the remaining fixes.

## What the present performance evidence says

The existing corrected held-out series has approximately 6.51% arithmetic
annualized return after the modeled 10 bp trading cost, at 5.56% annualized
volatility. Its net-return Newey-West t-statistic at 20 lags is about 2.21,
computed here from the existing daily artifact. These are descriptive figures
under the present accounting assumptions, not validated live expectations.

The locked book's corrected net Sharpe of 0.18 over the much longer selection
period provides weak support for durable profitability. Two strong later years
are worth investigating, but unresolved return marking and implementation
costs could materially change the result. The 40-candidate selection also
means the selection-period winner is an optimistically selected estimate.

Keep 2024–2025 for transparent correction audits. Any newly tuned strategy
needs a genuinely unexamined later period or prospective paper-trading record.
An independently fixed specification can be replayed to correct engineering
errors, but the already-observed period cannot become fresh evidence again.

## Practical improvement order

| Work | Estimated effort | Completion criterion |
|---|---|---|
| Correct IC nulls/ties/date ordering; add focused regressions | Half a day | Synthetic oracle and shuffled-input checks agree |
| Reconcile holdings, returns, executed trades, and cash | 1–2 days | Hand-calculated portfolios agree through entry, drift, expiry, and liquidation |
| Correct eligibility timing; separate formation from return marking | About a day | Full weights survive same-day input perturbation; holding returns remain available after entry restrictions change |
| Resolve event data and quantify missing-return exposure | 1–3 days plus data-access time | Explain material affected holdings and delisting payoffs; report sensitivity for unresolved events |
| Protect historical artifacts and update the report/environment | Half a day | A documented command reproduces each named version without rewriting another |

Start with the first two rows, then reassess. Do not spend weeks introducing
deep learning, a larger factor library, or a live execution service before the
evidence survives these checks. Full recomputation time is additional.

Once corrected, the next research additions with the most value are:

- **Attribution:** separate long/short contributions and regress portfolio
  returns on conventional market, size, value, momentum, and low-volatility
  exposures. Low market beta alone does not demonstrate stock-selection alpha.
- **Implementation sensitivity:** report short borrow fees/availability,
  spreads, trade size as a share of dollar volume, and a small set of capital
  scenarios. A constant basis-point cost cannot establish capacity.
- **Independent forward evidence:** freeze the revised rules and measure a
  later untouched or prospective period, including failures to obtain fills.
- **Actual neutrality diagnostics:** residualizing a score and then ranking
  or selecting deciles does not preserve exact regression orthogonality. Report
  realized portfolio exposures; impose weight constraints only if exact
  neutrality is the stated objective.

## CV positioning

Suggested bullet now:

> Built a CRSP equity research pipeline covering 21M daily observations, six
> interpretable signals, and ten purged walk-forward validation folds; audited
> portfolio accounting, transaction-cost sensitivity, and model-selection bias
> with 79 synthetic tests and documented correction analyses.

After fixes, add a clearly versioned out-of-sample result if useful. Being able
to explain why a strategy failed, how a bug changed its apparent performance,
and how the validation prevents recurrence is a stronger interview story than
presenting an unqualified Sharpe ratio.

## Review scope and reproducible evidence

- Ran `python -m pytest -q --disable-warnings`: **79 passed**, 193 warnings,
  approximately four seconds. Existing tests establish many local invariants
  but do not establish the accounting and statistical properties above.
- Added `reports/review_checks.py`: four tiny synthetic reproductions for
  drift, future-dependent formation membership, missing-target IC, and tied
  ranks. Run `python reports/review_checks.py`. These diagnostics deliberately
  confirm current defects; they are not passing correctness tests.
- Inspected source, existing tests, original and post-fix report artifacts,
  and read-only pre-2024 Parquet aggregates. Checked CRSP's official field
  documentation for delisting and return-duration semantics.
- Did not rerun the sealed test, rebuild raw data, refit models, change the
  strategy, or overwrite any pre-existing source/report changes. Only this
  review and its synthetic reproduction script were added.

Remaining uncertainty: the magnitude of the performance change after all fixes,
the original WRDS export's event completeness, actual shorting/execution costs,
and returns attributable to established risk factors remain unmeasured.
