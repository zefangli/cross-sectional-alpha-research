# Third review: verification of the event-return corrections

## Verdict

The event-ingestion, observed-return, resume-argument, and replay-output fixes
are verified. The reported performance figures reproduce. Two related issues
remain in portfolio state and the new execution diagnostic, so “all fourteen
were fixed” is still too broad. Gap execution was disclosed, not implemented.

This is a much stronger research project now. The remaining work can focus on
the portfolio engine and report diagnostics; another raw-data rebuild or model
refit is not inherently required for these two issues if the panels stay fixed.

## Verification completed

- **97 tests pass**, with 193 warnings; all four original review checks pass.
- A new read-only comparison against the raw export found **6,330 expected
  distinct event-return records for panel securities, zero missing from the
  cleaner, and zero differing returns**. The ingestion blocker is closed.
- All 6,330 event rows are ineligible for formation. PERMNO 80621's 2014-02-03
  return of -0.032161 is present and ineligible, as required.
- The observed-window column uses a trading-calendar RANGE window and retains
  known returns when the complete label is missing. The known-loss regression
  passes; the two quantities now travel separately into Week 2 evaluation.
- The audit runner passes explicit factor names. External replay targets now
  route output next to the targets file.
- A fresh **2014–2023 replay** matches all five corrected references:

| Metric | Independently replayed |
|---|---:|
| Gross Sharpe | 0.4934441164 |
| Net Sharpe, 10 bp | 0.1360259367 |
| Gross HAC t | 1.5297052095 |
| Market beta | -0.0570467450 |
| Maximum drawdown | -0.1705107089 |

- Recalculation from saved 2024–2025 daily returns matches gross Sharpe
  **1.4292244084**, net Sharpe **1.0582028089**, and net HAC t **2.0083611750**.
  This is a consistency check of the saved results, not a fresh sealed test.
- SHA-256 checks before and after the independent replay confirm the historical
  `reports/week6/` files and original locked specification are unchanged.
- The Git inclusion rules expose **155 untracked audit files totaling
  24,385,452 bytes (23.3 MiB)**. Keeping summaries, protocols, figures, and the
  locked book's daily series is a reasonable split. Nothing was staged,
  committed, deleted, or pushed by this review.

## Remaining finding 1 — P2: post-delisting allocations remain ordinary equity

**Location:** `src/portfolio/backtest.py:117–145`, `:165–177`.
**Affected description:** `README.md:62–65`.

The engine now recognizes the event return, but has no state transition for
the affected security afterwards. Its old cohort weights continue until their
scheduled expiry. The engine continues treating those allocations as equity
holdings, reporting missing returns and calculating trades to restore their
weights. A terminal payout needs to become cash or a defined successor claim;
the old security cannot remain an ordinary tradable position.

**Synthetic reproduction:** start a two-day cohort at +25% long and -25% short.
The long has a -100% delisting return on the first accrual day. The engine
correctly books a -25% portfolio return. The following day it still reports
50% gross exposure, including a +25% allocation to the wiped-out security,
and books a 25%-of-NAV purchase of that security as part of its rebalancing.
Reallocating to cash is not an equity trade in that security.

**Measured on the unchanged 2024–2025 locked book:** reconstructing cohort
weights and joining their missing-return days to the event records gives:

| Missing-return exposure, summed over dates | Weight-days |
|---|---:|
| All missing-return equity allocations | 2.5344924466 |
| After a recorded delisting event of any return status | 2.5311313593 |
| After a recorded event **with a nonmissing return** | 2.5213684291 |

Thus **99.48%** of the reported missing-return exposure occurs *after an event
whose return is known*. The advertised average of 0.51% of NAV does not mostly
represent securities for which no event return exists. Only about **0.00262%
of NAV per day** remains outside that known-event category. That residual is
not necessarily the final unresolved exposure: event settlement terms and
genuine gaps still need classification.

This does not reopen the ingestion finding; those returns are now present.
It demonstrates that the reported missing-data risk and some trading costs
still include allocations retained after the event. Where an event settles a
position into cash, applying an adverse missing-stock-return shock to that cash
is not a suitable estimate of missing-data risk. A known event return alone
does not establish the settlement type; that classification needs to be made
explicit. The effect of correcting portfolio state on headline Sharpe has not
been recomputed here.

**Required correction:** define and apply event settlement. Recognize the event
payoff once, transfer it into cash or a supported successor position, remove
the old security from subsequent equity targets and fills, and distinguish
any unresolved event claim from an observed settled payoff. Recalculate
turnover, equity exposure, and the missing-return sensitivity accordingly.
Add a -100% event test that asserts no later purchase of the old security.

## Remaining finding 2 — P2: the 0.62% execution diagnostic is one day off

**Location:** `src/portfolio/backtest.py:158–163`.

The engine labels row d with the return earned during day d, but its scheduled
trade occurs at the close of d-1. `traded_without_return` filters on `ret IS
NULL` for day d. It therefore examines the wrong day's information when used
to measure whether a booked trade has an observable execution close.

Two synthetic checks with a cohort formed on day 1 and first accrual on day 2:

| Input | Entry trade | Flagged as unobserved |
|---|---:|---:|
| Day-1 return missing; day-2 return observed | 0.50 NAV | **0.00 NAV** |
| Day-1 return observed; day-2 return missing | 0.50 NAV | **0.50 NAV** |

Even under the current missing-return proxy, the diagnostic flags the opposite
case to the execution-time question. Return availability alone is also an
imperfect execution proxy: delisting return rows can have a return but no
tradable closing price. A missing return need not mean there is no price.

The displayed fraction **0.62105%** does reproduce the saved diagnostic; it
does not yet validate the stated economic interpretation. Terminal
liquidation is added to total traded notional later and is not correspondingly
added to this diagnostic numerator.

**Required correction:** evaluate tradeability at the actual execution date
using available price/status/event information, preserving formation-day
observations even though they have no first-day P&L. Count terminal trades at
their own execution timestamp. Keep a distinct accrual-day missing-return
diagnostic if useful. Regenerate the reported fraction after settlement handling
and this timing fix.

## Scope and practical stopping point

For a quant CV, a documented research backtest with explicit approximations
can be useful; a full brokerage simulator is unnecessary. It should, however,
distinguish equity from settled cash and measure the disclosed execution
assumption on the correct date. These are bounded accounting and reporting
corrections, rather than a request to expand the model library.

The ordinary halt/gap execution assumption remains open: the engine still
assumes fills while a stock may be untradeable. It is now stated honestly in
the module docstring, which is an improvement. Classify it as a limitation,
not a fixed defect, until actual holdings/order deferral are implemented.

The additive transaction-cost overlay is also now explicitly described as an
approximation. I am not treating that disclosed simplification as a new blocker.
After the two issues above, refresh portfolio summaries and the public claim
to match what is actually validated. The current evidence still does not
establish live profitability.

Review artifacts are under `reports/review_round3_2026-09-15/`. I did not rerun
sealed mode, rebuild the full pipeline, refit models, or independently render
the PDF in this review. Source code and pre-existing report artifacts were
preserved.
