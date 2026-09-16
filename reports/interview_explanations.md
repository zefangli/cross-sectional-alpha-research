# Explaining this project: 30 seconds, 2 minutes, 5 minutes, 15 minutes

Four versions of the same honest story at four depths. Each is self-contained.
The discipline in all of them: lead with what was found, not with what was built,
and never state the result wider than the evidence carries.

---

## 30 seconds

I tested whether six well-known price and volume signals predict one-month
stock returns, on twenty years of CRSP data, with the last two years sealed
until the very end.

Almost everything was a null. Only one factor survived a multiple-testing
correction, none was tradable alone after costs, and machine learning models
lost to a simple equal-weighted composite. I locked one specification by a rule
I wrote down in advance, opened the sealed two years once, and it came out
positive and nominally significant after costs -- a gross Sharpe of 1.43, t of
2.71, net 1.06 at ten basis points.

That's a weak signal that passed a fair test once. Two years isn't enough to
call it alpha, and I don't.

---

## 2 minutes

**The question.** Do six interpretable cross-sectional signals -- momentum,
short-term reversal, realised volatility, volume surprise, residual momentum and
drawdown -- forecast 20-day returns well enough to trade after costs?

**The setup.** Twenty years of CRSP daily data, about 21 million rows, roughly
1,660 names per day after a point-in-time liquidity screen. Every factor is
fully determined by the previous day's close, so there's a full trading day
between signal and first return. 2024-2025 was sealed from the start and opened
exactly once.

**What I found, mostly nulls.** Of six factors, only realised volatility
survived Bonferroni on its information coefficient. Momentum was a flat null --
the fitted models even learned a negative loading on it, against the
pre-registered sign. No single factor was tradable after realistic costs.

Then OLS, Ridge and gradient boosting over ten walk-forward folds all *lost* to
an equal-weighted composite of pre-registered signs. Out-of-sample R-squared was
negative for all three: no point-prediction skill at all, only weak ordering.

**The part I'd actually talk about.** Risk-neutralising the book failed a test
I'd defined in advance. It removed 75 to 98 percent of market beta, as intended
-- but net-of-cost Sharpe got *worse* in seven of eight books, because
neutralisation halves the portfolio's volatility while the trading bill stays
identical. A fixed cost charged against half the risk budget doubles its bite.
You can't lever that away, because net Sharpe is leverage-invariant.

**The end.** I locked one specification by a rule declared in advance, applied
mechanically to 40 candidates, then ran the sealed two years once: gross Sharpe
1.43, HAC t 2.71, net 1.06 at 10 basis points, breakeven 38.5 basis points.
Positive and nominally significant. But two years, one selected specification,
and a cost model with no borrow, impact or capacity. It supports a narrow
claim and no more.

---

## 5 minutes

**Framing.** The interesting question in this kind of project isn't "can I find
a signal" -- it's "would I know if I hadn't". So the design work went into making
a null result detectable and a positive result trustworthy.

**Data and leakage control.** CRSP daily, 2005-2025, 21.1 million rows. A
point-in-time universe: price at least five dollars, twenty days of dollar volume
averaging five million, 252 prior returns, and a security classification read
from dated interval records rather than a header flag -- the header flag is a
survivorship trap, and I found the same trap again later in the SIC field, where
the header row matches the *first* interval more often than the last.

Two data facts that changed the factor definitions: price, volume and shares
outstanding are as-traded in this export while returns are split-adjusted, which
I verified on Apple's 2014 seven-for-one split. So volume surprise uses turnover
rather than raw share volume, and drawdown uses a cumulative total-return index
rather than price. Both have split-invariance tests.

Every factor is determined by the close of t-1. Two originally weren't -- they
used day-t information against a day-t target, which is leakage-free but implies
same-close execution. Lagging them cost volume surprise about a third of its
statistical significance. That's the general lesson: the more of a signal lives
in its most recent observation, the more of it is an execution assumption.

**Results, in order.** Six factors: one survives Bonferroni. Five of six show
hump-shaped decile returns, so the tails aren't where the signal is. Then the
cross-factor structure showed the factors weren't six bets: residual momentum
correlates 0.76 with momentum by portfolio return, and volatility and drawdown
correlate 0.87 despite ranking stocks nearly oppositely. Portfolio-return
correlation is the informative measure, not rank correlation.

Models: OLS, Ridge, gradient boosting, ten purged walk-forward folds, trained
only inside each fold. All three lost to the equal composite. The mechanism is
that they trade more for less -- a noisier signal self-cancels across the twenty
staggered daily cohorts, so a bigger share of the intended book nets away before
it's ever held.

A methodological finding I'd bring up unprompted: Ridge's penalty was
*unidentified* under mean-squared-error tuning. MSE fell monotonically out to
alpha of ten billion for a total improvement of 0.005 percent, because on a
20-day forward return MSE is almost all irreducible variance. But the penalty
still moved the portfolio -- predictions at alpha 1e4 and 1e10 correlate only
0.86 by daily cross-sectional rank, because Ridge rotates coefficients rather
than scaling them. MSE is the wrong criterion for a ranking problem. I kept the
pre-registered grid anyway rather than retuning after seeing that.

**Neutralisation and the lock.** Point-in-time sector, rolling beta and log
market cap, all at t-1, 100 percent coverage. Residualising the scores removed
almost all the beta and made net-of-cost performance *worse* in seven of eight
books, for the volatility-denominator reason above. I'd written the success
criterion in net terms in advance; on gross Sharpe alone, OLS and Ridge nearly
tripled and I'd have recorded a clean win.

The final specification was chosen by a rule fixed before any Week 5 result
existed -- maximise net Sharpe at 10 bp subject to realised beta within 0.10 of
zero -- applied mechanically to 40 candidate books. Twenty passed the beta
constraint. The winner drops residual momentum, which the ablation had already
flagged as the redundant half of the momentum pair.

**The sealed test.** One run. Gross Sharpe 1.43, HAC t 2.71, net 1.06 at 10 bp
(HAC t about 2.01), beta minus 0.063, max drawdown 3.6 percent, breakeven 38.5
bp. Those are the recomputed figures: the seal was opened once under the
pipeline as it then stood, and the numbers quoted are that same locked
specification rerun over the already-seen period after the engine was
corrected. Not a second sealed test, and I'd say so before quoting them.

**What I say about it.** It's a real out-of-sample result on a frozen
specification and it's nominally significant. It is also not significantly
*better* than the selection-sample estimate -- that difference has a t of about
1.5 -- the Sharpe interval runs roughly 0.4 to 2.5, the book was the best of
twenty correlated candidates, and the cost model has no borrow, impact or
capacity. Two adjacent positive years are consistency, not two experiments.

And the candidates were barely separated: on the corrected selection sample
the same rule would have picked `drop_vs_20__neutral__decile` (net Sharpe
0.157) over the locked book (0.136). I kept the lock, because re-selecting
after the seal was opened turns a pre-registered test into a fitted one. But
a ranking that flips under a bug fix is telling you the winner was one draw
from a cluster, not an identified best -- which is the more useful thing to
say about it.

**On turnover and delisting data, two things worth knowing about the engine.**
A daily-rebalanced book's real trade is target minus yesterday's *drifted*
holding, not target minus yesterday's target -- comparing targets alone
reports zero trading whenever targets are unchanged, even though restoring
them after a price move is itself a trade. Annual turnover is 10.4 times, and
breakeven is 38.5 bp under the correct comparison.

Separately, delisting returns exist in this CRSP export but are easy to miss:
in the CIZ flat-file format a delisting return is just a `DlyRet` row with
`DlyDelFlg = 'Y'`, and those rows carry placeholder classifications (security
type "N/A", price zero, no volume) that fail an ordinary common-share identity
screen. A query that filters on that same screen before checking for
delisting rows will conclude, wrongly, that none exist -- it confirms its own
premise. There are 11,824 such rows in the raw file, 11,445 with a return, and
the panel retains 7,042 of them against PERMNOs it already covers (see
`data_manifest.md` for the full handling). The general lesson: a verification
query built from the same assumption as the code it's checking proves
nothing; verifying completeness means scanning the raw file unfiltered.

---

## 15 minutes

Use the 5-minute version as the spine and add these, as the questions come.

**Why the seal mattered more than any single result.** The failure mode in this
kind of research isn't a bad model, it's a thousand small defensible choices
made while watching a number. The controls were: a pre-registration log written
before each week's runs; a final specification chosen by a rule declared in
advance; and a final test that could physically only run once. The last one was
enforced, not just intended -- an atomic marker file created before any sealed
data is opened, plus a check that the runner's own content at the recorded
commit is byte-identical to what's executing.

**The bug I'd most want to be asked about.** My first Week 4 design pre-ramped
each validation year's portfolio using a twenty-day warm-up block before the
year started. That block is exactly the window in which the training rows'
twenty-day forward targets are realised -- so a model trained through the cutoff
had already seen those returns, and forming positions there traded on them. Ten
folds meant ten contaminated stretches. Removing it cut the model books' Sharpe
by a third to a half, and cost the only positive net-of-cost result any model
had produced. The composite barely moved, because it depends on no fitted model
-- and that asymmetry is the mechanism confirming itself.

The one that would have been worse: the sealed runner derived its start date
from a helper whose default first validation year was 2014, so the final test
would have evaluated 2014-2025 and reported ten selection-sample years as the
held-out result. It would have looked entirely plausible. Caught in review before
the run.

**On turnover, precisely.** A daily-rebalanced book's real trade is target
minus *drifted* holding, W(t-1)(1+r)/(1+R_p), not target minus yesterday's
target -- comparing targets alone misses that restoring an unchanged target
after a price move is itself a trade. The engine computes it the first way. A
hand-calculated two-stock example through entry, drift and exit is in the test
suite to keep this pinned down.

**On what the engine still is.** A cost overlay on a daily-rebalanced target
book, not a cash-reconciled execution simulator: NAV growth uses the gross
return for every cost tier and costs come off additively. A delisted name is
settled to cash the day after its event -- one correctly-sized exit trade,
then zero equity exposure and zero missing-return flagging for that name --
rather than kept on the books as ordinary equity with a stale target weight
that the rebalancing math would otherwise try to "buy back." Where the
event's own return is unknown (one short position in the locked book, 0.056%
of NAV), the exit trade still happens but is measured and disclosed
separately (`gross_unknown_event_payoff`, `names_settled_unknown_payoff`)
rather than assumed to be a zero-return payoff. And the diagnostic that sizes
"trades with no observed execution price" checks only whether CRSP recorded a
return that day, nothing about price or trading status, so it's named for
exactly that: `traded_missing_execution_return`, 0.002% of notional. It is
not a tradability audit.

**On statistics.** Targets overlap twenty days, so every t-statistic is
Newey-West at twenty lags, computed on the series sorted by date -- an
unsorted series understates autocorrelation and inflates t. An iid Sharpe
approximation and a HAC test are not interchangeable; the HAC-consistent
interval is the one that governs, and an iid interval is at best a
sensitivity check, never a second correct answer. Slices are not to be
trusted either: a low-volatility tercile or a single strong year can show a
much larger t than the full sample, but that is the best of many possible
ex-post slices, not independent evidence -- and a tercile built on
full-sample quantiles isn't even implementable out of sample.

**On costs.** Breakeven is the number most people quote and it's the most
fragile thing in the study. Across four equally defensible holding periods --
5, 10, 20, 40 days, all declared in advance -- gross Sharpe barely moves but
breakeven swings from 10 to 38 basis points, because turnover falls fivefold. So
breakeven is a property of the holding period at least as much as of the signal.

**What I'd do next, and what I wouldn't.** I wouldn't analyse 2024-2025 further;
anything now is post-test. The honest next step is more out-of-sample time, or
the same protocol on a different market, which is a genuine replication rather
than another look at the same data. I'd also want borrow cost and a market-impact
model before anyone used the word deployable, and a capacity analysis -- the one
percent position cap never binds, so the book has never been tested at size.

**If asked what the project is really for.** It's a demonstration that I can run
a research process whose negative results are trustworthy. Most of the output is
nulls. The value is that the nulls are credible, the one positive result is
narrow and stated at its true width, and every choice that could have inflated it
is written down with a date attached.
