# Week 3 memo — cross-factor structure, validation design, and the baseline portfolio

**Date:** 2026-08-31
**Experiments:** `W3-001` … `W3-004`
**Sample:** cohorts formed 2006-02-01 to 2023-11-30; P&L marked 2006-02-02 to 2023-12-29
**Final test 2024–2025: not touched.** No model is fitted in this memo.

Reproduce with:

```
python src/features/build_factor_panel.py     # aligned six-factor rank panel
python src/evaluation/week3_baseline.py       # correlations, splits, portfolios
```

Outputs are in `reports/week3/`.

---

## 1. The aligned panel

One pass over the research panel produces all six factors, and an `aligned` flag
marks rows where an eligible stock has **all six** simultaneously available.
Percentile ranks are computed within date over the aligned rows only, so the six
ranks describe the same cross-section and are directly comparable.

| | |
|---|---|
| Panel rows | 21,104,236 |
| Eligible rows | 8,399,139 |
| Aligned rows | 8,319,133 (99.05% of eligible) |
| Mean names per aligned date | 1,660 |
| Minimum names on any date | 1,201 |
| First aligned date | 2006-02-01 |

Alignment deliberately does **not** require the forward target. The target is
needed for IC, but the portfolio marks positions to daily returns and would
otherwise lose the last 20 trading days of every run.

## 2. Cross-factor structure — the Week 2 question, answered

Week 2 ended by asking whether `mom_120_20`, `rvol_20`, `dd_252` and
`rmom_120_20` were four signals or one. They are close to one.

**Mean daily cross-sectional rank correlation:**

| | mom | rev_5 | rvol | vs_20 | rmom | dd |
|---|---|---|---|---|---|---|
| `mom_120_20` | 1.00 | −0.00 | −0.10 | 0.01 | **0.73** | **0.55** |
| `rev_5` | | 1.00 | −0.01 | −0.02 | −0.00 | −0.24 |
| `rvol_20` | | | 1.00 | −0.08 | −0.06 | **−0.48** |
| `vs_20` | | | | 1.00 | −0.00 | 0.05 |
| `rmom_120_20` | | | | | 1.00 | 0.28 |
| `dd_252` | | | | | | 1.00 |

**Daily gross portfolio-return correlation:**

| | mom | rev_5 | rvol | vs_20 | rmom | dd |
|---|---|---|---|---|---|---|
| `mom_120_20` | 1.00 | −0.17 | 0.46 | −0.08 | **0.76** | **0.75** |
| `rev_5` | | 1.00 | −0.32 | 0.05 | −0.14 | −0.43 |
| `rvol_20` | | | 1.00 | 0.17 | 0.33 | **0.87** |
| `vs_20` | | | | 1.00 | −0.03 | 0.05 |
| `rmom_120_20` | | | | | 1.00 | 0.50 |
| `dd_252` | | | | | | 1.00 |

Three things follow.

1. **`rmom_120_20` is mostly `mom_120_20`.** Rank correlation 0.73, return
   correlation 0.76. Residualising against the market removed very little of
   what momentum was measuring, which is consistent with Week 2's finding that
   the residual version is a null with the wrong sign — it inherited momentum's
   nothing and added estimation noise.
2. **Volatility and drawdown are nearly the same bet.** Their *ranks* correlate
   −0.48, but their long-short *books* correlate **+0.87**. Both end up long
   quiet stocks near their highs and short volatile stocks in deep drawdown.
3. **Return correlation is the informative measure, not rank correlation.**
   `mom_120_20` and `rvol_20` have rank correlation −0.10 — apparently
   independent — while their books correlate 0.46. Ranking stocks differently
   does not imply betting on different things: what matters is whether the
   resulting positions load on a common exposure, and here they do.

Only `rev_5` and `vs_20` are genuinely distinct. `vs_20`'s book has no return
correlation above 0.17 with anything.

The practical consequence is that an equal-weighted composite of six signed
ranks is not a six-way diversification. Its realised factor exposures confirm
this: 0.51 on momentum, 0.43 on drawdown, 0.40 on residual momentum, −0.31 on
volatility, but only 0.07 on volume surprise and 0.02 on reversal. **The
composite is three-quarters a bet on the correlated cluster and barely touches
the two signals that carry independent information.** That is an argument for
letting Week 4's models set the weights rather than assuming equality.

## 3. Walk-forward splits

Ten expanding-window folds, one validation year each, fixed here and written to
`reports/week3/walk_forward_splits.csv`:

| Fold | Train | Train days | Purge | Validation |
|---|---|---|---|---|
| 1 | 2006-02-01 → 2013-12-02 | 1,973 | 20 | 2014 |
| 2 | 2006-02-01 → 2014-12-02 | 2,225 | 20 | 2015 |
| … | | | | |
| 10 | 2006-02-01 → 2022-12-01 | 4,239 | 20 | 2023-01-03 → 2023-11-30 |

**The purge is the point.** A training observation at *t* carries a target
running to *t*+20, so training right up to the validation boundary would train
on returns realised inside the validation year. Training therefore stops 21
trading days early, which places the last training target on the final trading
day before validation begins. A test asserts that every fold has exactly 20
trading days between `train_end` and `validation_start`.

The final fold's validation stops at 2023-11-30, the last date whose target
window closes inside 2023, so no fold can reach the sealed period.

## 4. The baseline portfolio

Construction, per formation date, over the aligned cross-section:

1. cross-sectional percentile rank of the signal;
2. subtract the cross-sectional mean → the book sums to zero;
3. scale so gross exposure is 1;
4. cap each position at 1% of gross, then re-centre and re-clip.

The book formed at *t* is held for 20 trading days and a new one is formed every
day, so **20 cohorts are live at once**, each carrying 1/20 of the capital. P&L
is marked daily: the aggregate weight multiplies that day's close-to-close
return. This replaces Week 2's single-offset rebalance, which used one start
date in twenty and could flip a factor's sign on that choice alone.

Turnover and costs keep the Week 2 convention: TO = ½·Σ|ΔW|, cost charged on
traded notional Σ|ΔW|, so net = gross − 2·c·TO.

### Construction diagnostics

| | |
|---|---|
| Trading days | 4,508 |
| Mean positions | 1,732 |
| Mean net exposure | −0.002 (max 0.011) |
| Largest position ever | 0.35% against a 1% cap |
| Positions held with no return that day | 0.013 per day |

**The position cap never binds.** At ~1,700 names a rank-linear book puts about
0.12% in its largest position and 0.35% at the most concentrated. The cap is
retained for Week 4, where model-driven signals can be far more concentrated,
but it is doing nothing here and should not be described as a live constraint.

Net exposure is −0.2% of gross rather than exactly zero. Each cohort sums to
zero by construction, so the residual is stocks that leave the panel mid-holding
and whose weight disappears without being sold. It is small, but it is the same
delisting censoring documented in Week 1 showing up in the portfolio.

**Gross exposure is well below 1 for the fast signals** — 0.44 for `rev_5` and
0.39 for `vs_20`, against 0.93–0.96 for the slow ones. Nothing is wrong: the 20
live cohorts disagree about the same stock, and the long and short cohort
positions net out inside the book. A fast signal self-cancels when it is held
for twenty times its own half-life. Sharpe and breakeven cost are both
scale-invariant, so the comparisons below are unaffected, but the capital
efficiency is not: `vs_20` puts up a full unit of risk budget to hold 39% of a
book.

## 5. Results

Gross and net Sharpe on daily-marked returns, rank weighting:

| Signal | Gross | 1 bp | 5 bp | 10 bp | 20 bp | Turnover/yr | Breakeven |
|---|---|---|---|---|---|---|---|
| `vs_20` | **0.430** | 0.294 | −0.251 | −0.931 | −2.291 | 9.1× | 3.2 bp |
| `rev_5` | 0.323 | 0.272 | 0.070 | −0.182 | −0.686 | 8.6× | 6.4 bp |
| `composite` | 0.121 | 0.107 | 0.052 | −0.018 | −0.156 | 5.7× | **8.7 bp** |
| `rvol_20` | 0.081 | 0.070 | 0.029 | −0.023 | −0.126 | 5.1× | 7.8 bp |
| `dd_252` | 0.017 | 0.009 | −0.020 | −0.057 | −0.130 | 3.6× | 2.3 bp |
| `mom_120_20` | −0.006 | −0.016 | −0.058 | −0.111 | −0.217 | 4.1× | −0.5 bp |
| `rmom_120_20` | −0.052 | −0.071 | −0.144 | −0.235 | −0.418 | 4.5× | −2.9 bp |

The ordering of gross Sharpe is the ordering of Week 2's ICs, which is
reassuring: the portfolio machinery is not manufacturing anything. The composite
is the best net performer despite ranking third gross, because diversification
buys it the highest breakeven of any single-factor book.

**Nothing clears 10 bp.** The composite comes closest at −0.02, and is the only
signal still positive at 5 bp with a Sharpe above 0.05.

## 6. Exposures — dollar-neutral is not beta-neutral

| Signal | Market beta |
|---|---|
| `rvol_20` | **−0.34** |
| `dd_252` | −0.28 |
| `composite` | −0.23 |
| `mom_120_20` | −0.11 |
| `rmom_120_20` | −0.06 |
| `rev_5` | 0.05 |
| `vs_20` | 0.00 |

Every book sums to zero in dollars, and several still carry a large market beta.
`rvol_20` is short high-volatility stocks and long quiet ones, which is a
structurally short-beta position no dollar constraint can remove. The composite
inherits −0.23, and its rolling 252-day beta (`diagnostics.png`, bottom right)
is negative in **every** window of the sample, ranging from −0.01 to −0.41.

This matters for interpreting §5. A book with beta −0.23 earns part of its
return from market direction rather than from cross-sectional selection, and
over 2006–2023 that exposure was not free. Beta neutralisation is a Week 5
deliverable; until then, none of these Sharpes should be read as pure alpha.

## 7. Weighting: the rank baseline is not an improvement

Week 2 argued that rank-based continuous weights should capture more of these
signals than tail-decile books, because five of six factors have hump-shaped
decile returns. **That argument was wrong, and the ablation says so.**

Both weightings were run through the identical staggered-cohort estimator, so
the comparison isolates the weighting alone. Centring and gross-normalising a
+1/0/−1 decile indicator reproduces the equal-weighted D10−D1 book exactly.

| Signal | Gross SR, rank | Gross SR, decile | Turnover/yr, rank | decile |
|---|---|---|---|---|
| `mom_120_20` | −0.006 | **0.036** | 4.1× | 3.5× |
| `rev_5` | 0.323 | **0.404** | 8.6× | 7.1× |
| `rvol_20` | **0.081** | 0.024 | 5.1× | 4.3× |
| `vs_20` | 0.430 | **0.604** | 9.1× | 7.1× |
| `rmom_120_20` | −0.052 | **−0.017** | 4.5× | 3.9× |
| `dd_252` | **0.017** | 0.008 | 3.6× | 2.6× |
| `composite` | 0.121 | **0.147** | 5.7× | 8.3× |

**Decile weighting wins in five of seven cases, and it does so at lower turnover
in six of seven.** The best net-of-cost book in the whole study is the decile
composite: Sharpe 0.001 at 10 bp and a 10.1 bp breakeven, against −0.018 and
8.7 bp for the rank composite.

The Week 2 reasoning had the mechanism right and the conclusion backwards.
Hump-shaped deciles do mean a D10−D1 book sits on the two buckets where the
relationship breaks — but rank-linear weights do not avoid those buckets, they
just add the middle 80% of the cross-section, which carries little signal and a
lot of trading. Spreading weight across the interior dilutes rather than
rescues.

Rank weighting is nevertheless **retained as the declared Week 4 baseline**, per
the pre-registered plan. Switching the baseline now, after seeing which variant
won, is exactly the degrees-of-freedom problem the protocol exists to prevent.
Both weightings are carried into Week 4 so that the model comparison does not
rest on this choice.

## 8. Limitations

- **Costs are linear and flat.** A constant bp charge on traded notional ignores
  spread, participation and impact, all of which are worst in the small,
  volatile names these books concentrate in. Realised costs would be higher than
  modelled, and the 10 bp column is optimistic rather than conservative.
- **Exit handling.** A stock that leaves the panel mid-holding has its weight
  disappear rather than be liquidated. The effect is small (net exposure −0.2%)
  but it flatters turnover slightly and is the portfolio-level face of the Week 1
  delisting censoring.
- **No beta, sector or size neutralisation.** §6 shows how much that matters.
- **Execution at the close.** The one-day signal lag makes the positions
  tradable in principle, but P&L is close-to-close with no slippage.
- **One composite, chosen by assumption.** Equal weights over six signed ranks
  is a declared baseline, not an estimate. §2 shows it over-weights the
  correlated cluster.
- **No model has been fitted and no validation fold has been scored.** The
  splits exist; nothing has been run through them yet.

## 9. What Week 4 inherits

- `data/processed/factor_panel/` — 8.32M aligned rows with all six ranks.
- `src/models/splits.py` — ten fixed, purged, expanding folds through 2023.
- `src/portfolio/backtest.py` — dollar-neutral, capped, staggered-cohort book
  with daily P&L, turnover, costs and exposures, driven by any signal column.
- Two pre-declared weightings and a pre-declared composite to beat.

The bar for Week 4 is explicit: **a model must beat a gross Sharpe of 0.147 and
a 10.1 bp breakeven**, and it must do so out of sample across the ten folds. On
Week 2 and Week 3 evidence, the most likely honest outcome is that it does not
by much, and that whatever it does gain comes from weighting `rev_5` and `vs_20`
more heavily than an equal composite does — the two signals that are actually
independent of the rest.
