# Raw-data Manifest

| Field | Value |
|---|---|
| Provider | WRDS / CRSP |
| Local raw file | `crsp/yb8xejbnpiflaprb.csv` (ignored by Git; immutable) |
| WRDS query | Daily CRSP security file export containing point-in-time security classifications, daily price/return/capitalization/volume, distribution and delisting fields, and CRSP value-/equal-weighted and S&P market returns. Exact WRDS query text was not saved with the export; recover and append it before publishing. |
| Export file creation time (local) | 2026-08-24 23:32:08 -04:00 |
| Last modified time (local) | 2026-08-25 07:40:25 -04:00 |
| Data range | 2005-01-03 onward in the inspected first record; exact observed range is produced by `src/data/clean_crsp.py`. |
| Columns | 101 CSV columns; authoritative ordered header is preserved below. |
| File size | 23,076,151,863 bytes (23.08 GB decimal) |
| SHA-256 | `e336545a55b8029a10c34cdcdc8fb4065b345c9a630a793f9d321b2dacb93c1f` |

## CSV header (ordered)

`PERMNO, SecInfoStartDt, SecInfoEndDt, SecurityBegDt, SecurityEndDt, SecurityHdrFlg, HdrCUSIP, HdrCUSIP9, CUSIP, CUSIP9, PrimaryExch, ConditionalType, ExchangeTier, TradingStatusFlg, SecurityNm, ShareClass, USIncFlg, IssuerType, SecurityType, SecuritySubType, ShareType, SecurityActiveFlg, DelActionType, DelStatusType, DelReasonType, DelPaymentType, Ticker, TradingSymbol, PERMCO, SICCD, NAICS, ICBIndustry, NASDCompno, NASDIssuno, IssuerNm, YYYYMMDD, DlyCalDt, DlyDelFlg, DlyPrc, DlyPrcFlg, DlyCap, DlyCapFlg, DlyPrevPrc, DlyPrevPrcFlg, DlyPrevDt, DlyPrevCap, DlyPrevCapFlg, DlyRet, DlyRetx, DlyRetI, DlyRetMissFlg, DlyRetDurFlg, DlyOrdDivAmt, DlyNonOrdDivAmt, DlyFacPrc, DlyDistRetFlg, DlyVol, DlyClose, DlyLow, DlyHigh, DlyBid, DlyAsk, DlyOpen, DlyNumTrd, DlyMMCnt, DlyPrcVol, ShrStartDt, ShrEndDt, ShrOut, ShrSource, ShrFacType, ShrAdrFlg, DisExDt, DisSeqNbr, DisOrdinaryFlg, DisType, DisFreqType, DisPaymentType, DisDetailType, DisTaxType, DisOrigCurType, DisDivAmt, DisFacPr, DisFacShr, DisDeclareDt, DisRecordDt, DisPayDt, DisPERMNO, DisPERMCO, vwretd, vwretx, ewretd, ewretx, sprtrn`

## Integrity rule

Never open, modify, or re-export the raw file in place. Generated data must
be written under `data/processed/` and can always be rebuilt from this export.

## Initial cleaning audit

The first streaming audit found 1,594 duplicate `PERMNO`/date groups in the
eligible export. The cleaner retains one copy only when every selected panel
field is identical (`SELECT DISTINCT`); it does not arbitrarily resolve rows
that differ in retained fields. The cleaned-panel audit must report zero
duplicate groups before feature work.

## Delisting-return limitation

`DlyRet` is retained unchanged as the export's daily total return, including
the final observed row for each `PERMNO`.

In the CIZ flat-file format a delisting return is not a separate column: it is
a `DlyRet` observation whose `DlyDelFlg` is `Y`. The export contains 11,824
such rows (10,866 distinct PERMNO-dates; 908 duplicated pairs), 11,445 of them
with a return, ranging from -100% to +743%. Event rows carry placeholder
classifications (`USIncFlg` mostly `N`, `SecurityType = 'N/A'`,
`SecuritySubType = 'UNK'`, `ShareType = 'N/A'`, `TradingStatusFlg = 'D'`,
`PrimaryExch = 'X'`, price 0, no volume or capitalisation), so they do not pass
the common-share identity screen on their own.

The cleaner retains an event row for any PERMNO that has identity rows,
deduplicated to one row per (PERMNO, date) with an identity row winning a tie,
and preserves `delisting_flag`. Of the retained rows, 7,042 fall on PERMNOs
already in the panel (6,330 PERMNOs), every one dated after that PERMNO's last
regular row and 7,014 of them within five calendar days of it -- CRSP's
convention of dating the delisting return the trading day after the last
trade.

**Downstream handling.** An event row is never a formation row
(`build_research_panel.py`); the daily engine marks it like any other return
on the weight then held, and the observed-window return
`forward_return_20d_observed` includes it. The complete 20-day label
`forward_return_20d` still requires 20 following trading days, so a delisting
inside the window leaves the label NULL: labels stay complete-pair, marking
does not.

**Settlement.** `delisting_flag` is threaded through the factor panel to the
daily engine, which settles a name to cash the day after its event: a single
correctly-sized exit trade, then zero equity exposure and zero missing-return
flagging for that name. In the locked 2024-2025 book, residual missing-return
exposure -- from names not covered by this event data -- averages 0.0007% of
NAV per day.

**Unknown payoffs.** 175 of the 6,330 retained event rows have no recorded
return. The exit trade still happens, but treating a missing return as a
verified zero-return payoff is an assumption, not an observation, so these are
reported separately (`gross_unknown_event_payoff`,
`names_settled_unknown_payoff`) rather than folded into ordinary settlement.
In the locked 2024-2025 book this affects one short position (PERMNO 16795,
delisted 2024-10-28, no return, 0.056% of NAV).

**Return-duration flags.** Pre-2024 cleaned rows carry `DlyRetDurFlg` P1-P9
(a return spanning several trading days after missing rows; the event rows
themselves are mostly `DD`). They are kept as-is. The daily engine marks a
missing day at 0 and books the multi-day return on the day it lands *at the
weight then held*; that reproduces the cumulative P&L only if the book did not
change across the gap. Where a cohort expired or entered during the gap, the
engine has booked a trade in a name with no observation -- an execution
assumption, measured per day as `traded_missing_execution_return` and reported
with the results rather than claimed away. The 20-day label requires 20
consecutive rows, so any window containing the gap is NULL rather than
mis-compounded.

**Cleaner scope.** The cleaned panel keeps every row of every US common share
within its valid interval. Exchange, issuer type, conditional type and trading
status are entry-eligibility screens applied in `build_research_panel.py`, not
row filters here, so a name already held keeps being marked if it later halts,
moves exchange or delists.
