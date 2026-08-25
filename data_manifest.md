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
the final observed row for each `PERMNO`. In the filtered initial panel, 9,872
of 9,873 final rows have a nonmissing `DlyRet` (range -94.6872% to 435.2430%);
all `DlyDelFlg` values are `N`. This does **not** demonstrate that those final
returns include CRSP delisting returns: the export contains no separate
delisting-return variable. The 20-day target is therefore censored when fewer
than 20 later daily returns are observed. Obtain and merge explicit CRSP
delisting-return data before making claims about delisting-complete targets.
