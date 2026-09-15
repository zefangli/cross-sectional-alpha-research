# Fifth verification: disclosure corrections

## Verdict

The substantive corrections from round 4 are verified. No new blocking
finding in the changes reviewed. This is a reasonable stopping point for
the research/CV version, with its disclosed zero-return imputation, assumed
fills, and additive transaction-cost approximation. It is not evidence of
live profitability.

## Checks completed

- 101 tests pass, including the NULL-event regression and known-event
  exclusions; the four original review checks also pass.
- The settlement query carries the first event's own return, and the new
  fields count and size its unknown payoff once on the following day.
  The no-repurchase behavior is preserved.
- Fresh execution of the unchanged locked book on the already-seen
  2024–2025 audit period reproduces every numeric daily column and every
  saved summary field. The audit outputs therefore match current code,
  rather than merely having recent timestamps.
- Exactly one unknown-payoff settlement is reported, on 2024-10-29:
  `gross_unknown_event_payoff=0.000559151895378284`, count 1. The independent
  cohort reconstruction identifies PERMNO 16795, event date 2024-10-28,
  signed event weight -0.0005578032548775814. The small difference in weight
  is expected: the settlement diagnostic divides by event-day book NAV.
- Gross Sharpe 1.4292244084, net Sharpe at 10 bp 1.0582559258, and breakeven
  38.5269103547 bp match the previous round to numerical tolerance.
- Active code uses `traded_missing_execution_return`; the main descriptions
  explicitly distinguish return availability from price/status/fill evidence.
- The current saved pre-2024 replay matches all five targets and agrees with
  the previous round's independently replayed values. A fresh full pre-2024
  replay was not repeated in this round.
- Original sealed artifacts and lock match the SHA-256 inventory recorded
  in round 4 and remain unchanged after this verification.

## Nonblocking finishing notes

1. README's concluding paragraph still calls the 0.002% statistic
   "unobserved-execution" exposure. Use "missing execution-date return"
   there as well, consistent with the corrected explanation above it.
2. The explicit event-payoff sensitivity suggested in round 4 is not present.
   A short example would complete the disclosure: for this short position,
   a hypothetical event return of -100% instead of the imputed 0% adds about
   5.58 bp of event-day portfolio return; +100% subtracts about 5.58 bp,
   before changes to costs and subsequent NAV normalization. These are
   scenarios, not a bound on a short position's loss or a full Sharpe rerun.

Neither note calls for another model fit, raw-data rebuild, or strategy
selection. The new total of 18 cited findings is arithmetically consistent.

Evidence from this verification is under `reports/review_round5_2026-09-15/`.
It reuses round 4's verification script with its output directory redirected,
preserving the earlier evidence. No source implementation or existing report
was edited. The PDF layout and the detached-job/memory-pressure account were
not independently verified. Nothing was staged, committed, or pushed.
