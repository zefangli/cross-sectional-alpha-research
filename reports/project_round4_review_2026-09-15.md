# Fourth review: settlement and execution-date verification

## Verdict

The main corrections work: known delisting returns are marked, wiped-out
securities are no longer repurchased, and the return-availability diagnostic
checks the proper execution date, including terminal liquidation. The reported
performance and diagnostic numbers reproduce. Two narrower parts of the prior
findings remain unresolved: unknown event payoffs are treated as known cash,
and return availability is still described as observed execution prices.

These are bounded accounting/disclosure corrections. They do not justify
another raw-data rebuild, model refit, or strategy selection. For the CV goal,
explicit assumptions and correctly named diagnostics are a reasonable stopping
point; a full execution simulator is unnecessary. This evidence does not
establish deployable profitability.

## Verified independently

- `python -m pytest -q`: **100 passed**, 193 existing sklearn deprecation warnings.
- `python reports/review_checks.py`: all four original checks pass.
- Fresh 2014–2023 replay matches all five corrected targets:

| Metric | Replayed |
|---|---:|
| Gross Sharpe | 0.4934706900 |
| Net Sharpe, 10 bp | 0.1361720461 |
| Gross HAC t | 1.5297708421 |
| Market beta | -0.0570461374 |
| Maximum drawdown | -0.1705107089 |

- Fresh execution of the unchanged locked book over the already-seen
  2024–2025 audit period reproduces every numeric column of the saved daily
  series (`rtol=1e-8`, `atol=1e-10`). This is a correction verification, not a
  new sealed test. Recomputed summaries include:

| Metric | Recomputed |
|---|---:|
| Gross Sharpe | 1.4292244084 |
| Net Sharpe, 10 bp | 1.0582559258 |
| Breakeven cost | 38.5269103547 bp |
| Missing-return positions/day | 0.0079840319 |
| Missing-return gross exposure/day | 0.0006708757% of NAV |
| Maximum missing-return gross exposure | 0.1973040577% of NAV |
| Trade notional with a missing return at execution date | 0.0020068980% |

- Known -100% and partial-loss settlement regression tests pass. The new lag
  is calculated before filtering to live positions, preserving the entry
  trade's predecessor. Terminal liquidation also enters the diagnostic numerator.
- SHA-256 checks around the completed audit verification show the original
  `reports/week6/` files and locked specification unchanged. Git also reports
  no difference from HEAD for those paths.

## Remaining P2: distinguish unknown event proceeds from observed settlement

**Location:** `src/portfolio/backtest.py:153–164`, `:195–198`.

`settled` selects every `delisting_flag='Y'` row without checking whether its
return is known. A NULL event return accrues zero and drifts at zero, then the
whole prior marked value is removed to assumed cash. Equity removal is right;
the implied full-value recovery and disappearance of unresolved payoff risk
are not observations established by the event flag.

This is a real input case: **175 of the 6,330 retained event rows have NULL
returns**. The 2024–2025 locked book holds 194 distinct event rows, including
one with a missing return:

| PERMNO | Event date | Return | Signed event weight |
|---|---|---|---:|
| 16795 | 2024-10-28 | NULL | -0.0005578032549 |

That is a short claim worth **0.05578% of NAV**, or 5.58 basis points of NAV.
This is its event-date exposure, not a measured loss, a risk bound, or a daily
average. Its unknown payoff cannot be validated by the smaller post-settlement
`gross_without_return` statistic.

A minimal synthetic reproduction also confirms the policy: a +50%-NAV
holding with a NULL event return books zero P&L on the event day, then a
50%-NAV exit and zero remaining exposure the next day. That is an assumed
zero event return, not an observed payout.

**Smallest sufficient correction:** keep the no-repurchase rule, explicitly
separate known event proceeds from unknown event claims, report missing-payoff
count and exposure, and state the return/settlement assumption with an event
payoff sensitivity. A disclosed zero-return imputation is acceptable for a
research approximation; describing it as verified cash settlement is not.
Add a NULL-event regression. Do not restore stale tradable equity targets.

## Remaining P2: the 0.002% statistic is not an execution-price audit

**Location:** `src/portfolio/backtest.py:199–202`;
`README.md:72–76`; `reports/final_report.md:517–520`.

The timestamp correction is verified, but the predicate is still
`ret_prev IS NULL` (and `ret IS NULL` for terminal liquidation). The calculation
does not inspect price, trading status, or whether a flow is cash settlement.
A nonmissing return is not an observed executable price; retained delisting
event records themselves illustrate this distinction, with event returns and
zero prices. Conversely, a missing return need not establish a missing price.

The README and limitations section nevertheless call this the fraction with
"no observed execution price." The number reproduces; that interpretation
does not follow from its inputs.

**Smallest sufficient correction:** label it "traded notional whose execution
date has a missing return" and explicitly call it a limited availability
proxy. Withdraw claims that it measures untradeable notional or verifies
fills. If an actual price/status diagnostic is desired, build that separately
and distinguish cash settlements from market orders. Neither option requires
refitting models.

## Minor documentation correction

The cited review counts are nine plus five plus two: **16 findings**, not 19.
The final report also enumerates 1–16. Correct the total or explain a different
counting convention. Disclosed execution approximations should not be called
implemented fixes.

## Scope and artifacts

Evidence is in `reports/review_round4_2026-09-15/`: replay results, independently
recomputed audit summary, held-event inventory, hashes, and `verify.py`.
The verification script supports `--events-only` and `--audit-only` for
bounded reruns. An initial review-script CSV-writer error occurred after the
daily comparisons passed; it was fixed and the audit verification rerun
successfully. It was not a project pipeline error.

The old `event_exposure_check.py` reconstructs the pre-settlement static
allocation for the earlier finding. Rerunning it documents that original
problem; it does not itself test the corrected settlement engine.

No source implementation, existing documents, lock, or sealed outputs were
changed by this review. Nothing was staged, committed, or pushed. The raw
export was not rescanned and the PDF was not independently rendered here;
this review focused on the latest engine changes and numerical claims.
