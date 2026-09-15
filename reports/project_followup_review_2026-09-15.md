# Follow-up review of the implemented corrections

## Verdict: substantial progress, but not ready for sign-off

The reported figures reproduce under the current implementation. Most original
code corrections are present and work. However, the conclusion that the raw
export contains no usable delisting observations is wrong: an identity filter
removes event records for securities actually held by the strategy. This is the
main remaining blocker. Existing corrected performance figures need another
labeled audit after that ingestion/valuation issue is fixed.

This review changed no strategy code or existing results. Review evidence is in
`reports/review_validation_2026-09-15/`.

## What independently passed

- `python -m pytest -q --disable-warnings`: **89 passed**, 193 warnings.
- `python reports/review_checks.py`: all four original reproductions now pass.
- Fresh **2014–2023 replay** from the current panels and source, with output
  redirected into the review directory to preserve historical files:

| Metric | Fresh replay | Matches corrected target |
|---|---:|---|
| Gross Sharpe | 0.4869505231 | Yes |
| Net Sharpe at 10 bp | 0.1293080864 | Yes |
| Gross HAC t | 1.5093513270 | Yes |
| Market beta | -0.0570741574 | Yes |
| Maximum drawdown | -0.1702126179 | Yes |

- Recalculating gross/net metrics from the saved 2024–2025 daily audit matches
  its summary: gross Sharpe **1.42943**, net Sharpe at 10 bp **1.05815**, net HAC
  t **2.00649**. This validates consistency with the saved returns, not their
  underlying economic completeness.
- Subtracting 1% of daily `gross_without_return` reproduces the described
  adverse scenario: net Sharpe **0.80674**, a reduction of **0.25141**.
- The original `reports/week6/` artifacts and original locked specification
  have no changes relative to Git HEAD. The historical commits cited in the
  report do share the stated `src/` tree hash.
- Complete-pair average-rank IC, chronological sorting before HAC, lagged
  eligibility, and default protection of the existing lock are implemented.

## Remaining findings

### 1. P1 — The cleaner still drops available delisting returns

**Code:** `src/data/clean_crsp.py:66–69`, `:113`.
**Incorrect explanation:** `data_manifest.md:38–52` and the completion report.

An unrestricted scan of the raw 23 GB CSV found:

| Raw DlyDelFlg | Rows |
|---|---:|
| N | 40,400,550 |
| Y | **11,824** |

Of the 11,824 event rows, **11,445 have a nonmissing return**. All 11,824 satisfy
the classification-date interval check; **none satisfy the current common-share
identity predicate**. Example event records carry `USIncFlg=N`,
`SecurityType=N/A`, `SecuritySubType=UNK`, `ShareType=N/A`, and
`TradingStatusFlg=D`. These are event-row classifications, not evidence that
the security was outside the investable universe before its delisting.

Joining by PERMNO to securities that were aligned/eligible before 2024 produces
**2,816 distinct (PERMNO, date, return) event records in 2005–2023**, of which
**2,781 have nonmissing returns**. The counts above distinguish raw rows from
deduplicated records; simply appending all raw event rows would risk duplicates.

**Concrete actual holding:** PERMNO **80621** has a raw delisting return of
**-0.032161 on 2014-02-03**. The cleaned panel ends at 2014-01-31. It had 12
aligned formation dates in the preceding 20 trading days. Reconstructing the
unchanged locked book gives an event-day target weight of **+0.0018201761**.
The dropped event therefore omits approximately **-0.5854 basis points of
portfolio return on that date**, measured at the engine's current target
weight. This is actual strategy exposure, not merely an unrelated raw record.

The previous audit conditioned on the very identity filter responsible for
the omission, then concluded that the data did not exist. Relaxing exchange
and active-status filters did not fix this remaining identity-filter problem.

**Required correction:** preserve and deduplicate the event-return stream by
PERMNO/event date, associate it with the security's pre-event identity, and
apply its payoff to outstanding holdings. Keep formation eligibility separate;
event rows must not create new tradable positions. Verify event timing and
avoid double-counting any return already recognized. Rebuild the affected
panels/results and correct the manifest and headline caveats.

CRSP documents the special convention of storing daily delisting information
on the trading day after the delisting date. Its event records need explicit
handling rather than the ordinary row-identity assumption. See
[CRSP's CIZ convention documentation](https://www.crsp.org/wp-content/uploads/appendix/FlagType_MU.html).
Reproduction queries are saved in `review_validation_2026-09-15/raw_delisting_audit.sql`.

### 2. P1 — Week 2 erases known returns when the full target is unavailable

**Code:** `src/evaluation/factor_eval.py:131–139`.

Separating formation from future target availability is correct. But the new
`portfolio()` replaces a missing 20-day target with zero for the **whole
period**. That is not equivalent to retaining observed daily returns and
assuming zero only on missing days, despite the module's claim that it uses
the same policy as the daily engine.

**Reproduced through the actual target builder:** a stock with ten subsequent
observed days, including a -50% last observed return, receives a NULL 20-day
target because its data then end. A +100% long position and a flat short leg
produce **zero gross return** in Week 2. Even under the stated flat-mark
assumption for the remaining days, the known long loss is **-50%**.

**Required correction:** calculate portfolio P&L from observed daily/event
returns, with an explicit policy for the genuinely unknown portion. Keep the
complete 20-day label requirement for IC/model labels separately. Do not
replace a partly observed holding period with an entirely flat return.

### 3. P2 — Gap-return accounting still assumes executable trades during gaps

**Code:** `src/portfolio/backtest.py:106–114`, `:144–150`.
**Overstatement:** `data_manifest.md:55–60` says cumulative gap P&L is correct.

The engine changes target holdings and closes expired cohorts even when a
stock has no price/return observation. A later multi-day return is multiplied
by the then-current target weight, or missed entirely if the cohort expired.
Thus recording zero on missing days does not in general preserve cumulative
P&L when holdings change across the gap.

**Reproduced:** a two-day cohort experiences a halt/gap on days 2–3 and a -50%
recovery return on day 4. The engine closes it on day 3 at the carried value,
reports zero total gross return, and never recognizes the day-4 loss. Such an
exit requires an executable trade that the data do not establish.

This is not only a theoretical class of input: pre-2024 P1/P2 return-duration
events occur after recent aligned formations, including PERMNO 80539 on
2014-06-13 (P2) and PERMNO 88545 on 2014-02-13 (P1). Their actual portfolio
impact has not been recomputed here.

**Required correction:** distinguish target orders from executable holdings.
For genuine halts, defer fills until execution is possible and recognize
subsequent returns/payoffs on actual outstanding positions. For missing data
without a confirmed halt, state and stress the execution assumption. Until
then, remove the blanket claim that multi-day-gap P&L is correct.

### 4. P2 — Resuming the correction runner fails at Week 2

**Code:** `src/evaluation/run_post_fix_audit.py:123–128`;
`src/evaluation/factor_eval.py:main`.

`run_post_fix_audit.py --from-step 6` parses the resume flag and then calls
`factor_eval.main()`. That function reads the unchanged process-wide
`sys.argv[1:]` as factor names. It consequently tries to evaluate the factor
`--from-step` and raises **`KeyError('--from-step')`**. Resuming at any earlier
step also eventually hits this failure. The no-argument full run can work.

**Verified:** invoked `run_week2()` with the real argument vector and a
temporary report directory; it raises that exact exception before evaluation.

**Minimal fix:** accept explicit factor arguments in the called entry point,
and pass an empty/default list from the audit runner. Add a test exercising the
resume path through the Week 2 boundary without running the expensive stages.

### 5. P2 — Corrected replay still writes into the historical report directory

**Code:** `src/evaluation/week6_final.py:63`, `:492–498`.
**Documentation:** `README.md:152–156`.

The new replay-target argument changes expected metrics but leaves `OUT` set
to `reports/week6`. The documented corrected replay therefore overwrites
`replay_validation.csv` and `replay_protocol.json` in the original record.
It does not overwrite `final_daily.csv` or the one-shot marker, but it violates
the promise that this workflow never touches that directory.

The stage-by-stage commands also continue to write evaluations into original
`reports/week2`-style/root factor locations and `reports/week3–5`, whereas the
README describes them as rebuilding the current version. Those destinations
must be explicit to avoid mixing current calculations with historical records.

**Minimal fix:** route corrected replay and stage-by-stage outputs to the audit
tree, or expose an explicit output-directory argument. Verify historical files
remain byte-identical after replay. The independent replay in this review
explicitly redirected output to avoid altering the originals.

## Small remaining modeling qualification

The drift calculation now correctly recognizes price-driven changes in gross
holdings. It still uses a gross-return NAV denominator shared by all cost
scenarios, and subtracts costs additively. Thus it remains an approximate cost
overlay rather than a fully reconciled cash/NAV execution simulator. Terminal
liquidation also uses an end-of-day NAV fraction in the same `traded` field as
start-of-day trades. Document the approximation or reconcile the units if
claiming exact accounting. These effects have not been measured and are lower
priority than the demonstrably omitted returns above.

## What to do next

1. Correct event ingestion and known-return preservation before another full
   recomputation. Add regression examples with delisting-row identity
   placeholders, partially observed holding periods, and a halt across expiry.
2. Fix resume argument handling and output routing; both are small changes.
3. Recompute the same locked specification into a new labeled correction audit,
   retaining the previous snapshots. Reassess significance after actual event
   returns are included. Do not reselect the book based on this audit.
4. Replace “all nine fixed” with a precise status until these checks pass.

## The three housekeeping decisions

- **74.3 MB of audit outputs (about 70.9 MiB):** keep summaries, protocols,
  replay targets, figures, and regression tests in Git. Keep large daily files
  in a versioned compressed archive/release or Git LFS if they should be
  distributed, with checksums and a reproduction command. Do not blanket-ignore
  the entire audit directory: that would also lose evidence needed to assess
  the claims. This review did not stage or remove files.
- **`_debug_post_fix.py`:** no references were found elsewhere in the scanned
  project. It can be removed after confirming it is not needed for a manual
  workflow; it was left untouched during review.
- **Git ownership:** plain `git status --porcelain` succeeded in this review
  environment, with warnings about the global ignore file rather than a
  dubious-ownership rejection. I did not change ownership or Git configuration.
  Recheck under the account used to commit before applying a configuration fix.

## Limits of this verification

I ran the tests, original reproductions, a fresh pre-2024 replay, two full
read-only raw scans, focused raw/processed joins, and the synthetic checks
described above. I did not rebuild all stages, refit the models, rerun sealed
mode, or independently re-render/visually inspect the PDF. The aggregate impact
of restoring delisting events remains unmeasured.
