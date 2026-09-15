"""Regressions for the 2026-09-15 follow-up review."""
from datetime import date, timedelta
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd

from src.data.clean_crsp import clean_query
from src.evaluation.factor_eval import factor_names, portfolio
from src.evaluation.week6_final import OUT as W6_OUT, replay_out_dir
from src.portfolio.backtest import daily_book

RAW_COLUMNS = ["PERMNO", "DlyCalDt", "DlyRet", "DlyPrc", "DlyVol", "DlyCap", "ShrOut", "vwretd",
               "DlyRetx", "SecInfoStartDt", "SecInfoEndDt", "PrimaryExch", "USIncFlg",
               "SecurityType", "SecuritySubType", "ShareType", "IssuerType", "ConditionalType",
               "TradingStatusFlg", "SecurityActiveFlg", "DlyDelFlg", "DlyRetMissFlg", "DlyRetDurFlg"]


def raw_row(permno, day, ret, event=False):
    d = f"2014-01-{day:02d}"
    identity = ("N", "N/A", "UNK", "N/A", "N/A", "N/A", "D") if event else \
               ("Y", "EQTY", "COM", "NS", "CORP", "RW", "A")
    return [str(permno), d, ret, "10", "1000", "100", "10", "0.0", ret, "2013-01-01", "2015-01-01",
            "N", identity[0], identity[1], identity[2], identity[3], identity[4], identity[5],
            identity[6], "Y", "Y" if event else "N", "NA", "D1"]


def test_cleaner_keeps_delisting_event_rows_for_panel_securities_only():
    """Item 1: the event row carries placeholder classifications and must be
    kept for a PERMNO the panel knows, deduplicated, and dropped otherwise."""
    rows = [raw_row(1, 2, "0.01"), raw_row(1, 3, "0.02"),
            raw_row(1, 6, "-0.032161", event=True), raw_row(1, 6, "-0.032161", event=True),
            raw_row(9, 6, "-0.5", event=True)]          # never an identity row
    con = duckdb.connect()
    con.register("raw", pd.DataFrame(rows, columns=RAW_COLUMNS))
    out = con.sql(clean_query("raw")).df().sort_values(["permno", "date"])
    assert out.permno.tolist() == [1, 1, 1]
    assert out.delisting_flag.tolist() == ["N", "N", "Y"]
    assert abs(out.ret.iloc[-1] - -0.032161) < 1e-12
    assert not out.duplicated(["permno", "date"]).any()


def test_identity_row_wins_when_an_event_row_shares_its_date():
    rows = [raw_row(1, 2, "0.01"), raw_row(1, 3, "0.05"), raw_row(1, 3, "-0.9", event=True)]
    con = duckdb.connect()
    con.register("raw", pd.DataFrame(rows, columns=RAW_COLUMNS))
    out = con.sql(clean_query("raw")).df().sort_values("date")
    assert len(out) == 2 and abs(out.ret.iloc[-1] - 0.05) < 1e-12


def test_observed_forward_return_keeps_known_returns_when_the_label_is_incomplete():
    """Item 2: ten observed days ending in -50% then nothing. The complete
    label is NULL; the marking return compounds what was seen."""
    from tests.test_research_panel import panel, rows
    r = rows(11)
    r[10] = (*r[10][:2], -0.5, *r[10][3:])
    filler = [tuple([2, *row[1:]]) for row in rows(40)]
    out = panel(r + filler)
    stock = out[out.permno == 1].sort_values("date").reset_index(drop=True)
    assert np.isnan(stock.loc[0, "forward_return_20d"])
    assert abs(stock.loc[0, "forward_return_20d_observed"] - ((1.01 ** 9) * 0.5 - 1)) < 1e-12
    assert np.isnan(stock.loc[10, "forward_return_20d_observed"])   # nothing follows


def test_delisting_event_row_is_never_a_formation_row():
    from tests.test_research_panel import panel, rows
    r = rows(300, final_delisting_return=-0.3)
    out = panel(r).sort_values("date").reset_index(drop=True)
    assert out.loc[298, "eligibility_flag"]
    assert not out.loc[299, "eligibility_flag"]
    assert out.loc[299, "delisting_flag"] == "Y"


def test_week2_portfolio_marks_the_observed_return_not_the_missing_label():
    weights = pd.DataFrame({"date": ["d1"] * 2, "permno": [1, 2], "w": [1.0, -1.0],
                            "y": [-0.5, 0.0], "y_label": [np.nan, 0.0]})
    book = portfolio(weights)
    assert abs(book.gross_return.iloc[0] - -0.5) < 1e-12
    assert book.names_without_target.iloc[0] == 1
    assert book.names_without_any_return.iloc[0] == 0


def test_trades_booked_in_unobserved_names_are_measured():
    """Item 3: a two-day cohort whose name has no rows on days 2-3 is closed
    by the engine on a day it cannot trade. That trade is reported, not hidden."""
    dates = pd.bdate_range("2020-01-01", periods=6)
    rows_ = []
    for t, d in enumerate(dates):
        rows_.append(dict(permno=2, date=d, tdi=t, ret=0.0, value_weighted_market_return=0.0,
                          delisting_flag="N"))
        if t not in (2, 3):
            rows_.append(dict(permno=1, date=d, tdi=t, ret=-0.5 if t == 4 else 0.0,
                              value_weighted_market_return=0.0, delisting_flag="N"))
    con = duckdb.connect()
    con.register("panel", pd.DataFrame(rows_))
    con.register("cohort", pd.DataFrame({"permno": [1], "tdi": [0], "w": [1.0]}))
    book = daily_book(con, "panel", "2020-01-01", "2020-02-01", hold=2).set_index("tdi")
    assert book.traded_missing_execution_return.loc[3] > 0   # the expiry trade at t=3
    assert abs(book.traded_missing_execution_return.loc[3] - book.traded.loc[3]) < 1e-12
    assert book.traded_missing_execution_return.loc[1] == 0


def test_settlement_stops_repurchasing_a_wiped_out_security():
    """Round 3, finding 1: a single-name cohort with a -100% delisting return
    on its first accrual day. The day after, the engine must not report
    exposure to, or a purchase of, the dead security -- a single name isolates
    this from the ordinary small rebalancing trade a surviving offsetting leg
    would need once the book's own NAV has moved (see the partial-loss test
    below for that case)."""
    dates = pd.bdate_range("2020-01-01", periods=6)
    rows_ = [dict(permno=1, date=d, tdi=t,
                  ret=-1.0 if t == 1 else 0.0,
                  value_weighted_market_return=0.0,
                  delisting_flag="Y" if t == 1 else "N")
             for t, d in enumerate(dates)]
    con = duckdb.connect()
    con.register("panel", pd.DataFrame(rows_))
    con.register("cohort", pd.DataFrame({"permno": [1], "tdi": [0], "w": [1.0]}))
    book = daily_book(con, "panel", "2020-01-01", "2020-02-01", hold=2).set_index("tdi")
    assert abs(book.gross_return.loc[1] - -0.5) < 1e-12   # event recognised normally: -100%/hold
    row = book.loc[2]
    assert row.traded < 1e-9          # no repurchase of the wiped-out name
    assert row.gross_exposure < 1e-9  # no more equity exposure to it
    assert row.positions == 0
    assert 3 not in book.index or book.gross_exposure.loc[3] == 0   # stays settled
    # A KNOWN event return (-100%, not NaN) must not be flagged as an unknown payoff.
    assert row.gross_unknown_event_payoff < 1e-9
    assert row.names_settled_unknown_payoff == 0


def test_settlement_liquidates_a_partial_delisting_return_into_cash():
    """A -30% (not total-loss) event should trade the drifted survivor value
    to cash the next day, then report zero exposure from then on."""
    dates = pd.bdate_range("2020-01-01", periods=6)
    rows_ = [dict(permno=1, date=d, tdi=t,
                  ret=-0.3 if t == 1 else 0.0,
                  value_weighted_market_return=0.0,
                  delisting_flag="Y" if t == 1 else "N")
             for t, d in enumerate(dates)]
    con = duckdb.connect()
    con.register("panel", pd.DataFrame(rows_))
    con.register("cohort", pd.DataFrame({"permno": [1], "tdi": [0], "w": [1.0]}))
    book = daily_book(con, "panel", "2020-01-01", "2020-02-01", hold=2).set_index("tdi")
    w = 0.5                              # weight = 1.0 / hold(2)
    book_ret_event = w * -0.3            # the single name's own event-day book return
    drifted = w * (1 - 0.3) / (1 + book_ret_event)
    assert abs(book.traded.loc[2] - drifted) < 1e-12   # sells the drifted survivor value
    assert book.gross_exposure.loc[2] < 1e-9
    assert 3 not in book.index or book.gross_exposure.loc[3] == 0
    assert book.gross_unknown_event_payoff.loc[2] < 1e-9   # known return, not flagged
    assert book.names_settled_unknown_payoff.loc[2] == 0


def test_unknown_event_payoff_is_disclosed_not_hidden():
    """Round 4, finding 1: a NULL event return must not be silently treated as
    an observed zero-return settlement. The exit trade still happens (a stale
    equity target is never restored), but it is counted separately as an
    assumed, not observed, payoff -- matching the reviewer's own synthetic
    reproduction: a +50%-NAV holding with a NULL event return books zero P&L
    on the event day, then a 50%-NAV exit and zero remaining exposure next."""
    dates = pd.bdate_range("2020-01-01", periods=6)
    rows_ = [dict(permno=1, date=d, tdi=t,
                  ret=np.nan if t == 1 else 0.0,
                  value_weighted_market_return=0.0,
                  delisting_flag="Y" if t == 1 else "N")
             for t, d in enumerate(dates)]
    con = duckdb.connect()
    con.register("panel", pd.DataFrame(rows_))
    con.register("cohort", pd.DataFrame({"permno": [1], "tdi": [0], "w": [1.0]}))
    book = daily_book(con, "panel", "2020-01-01", "2020-02-01", hold=2).set_index("tdi")
    w = 0.5   # weight = 1.0 / hold(2)
    assert abs(book.gross_return.loc[1] - 0.0) < 1e-12          # unknown accrues 0, not a loss
    assert abs(book.traded.loc[2] - w) < 1e-12                  # exit trade still happens
    assert book.gross_exposure.loc[2] < 1e-9                    # no repurchase either way
    # But this exit is an ASSUMED zero-return payoff, not an observed one:
    assert abs(book.gross_unknown_event_payoff.loc[2] - w) < 1e-12
    assert book.names_settled_unknown_payoff.loc[2] == 1


def test_traded_missing_execution_return_checks_the_execution_day_not_the_accrual_day():
    """Round 3, finding 2: the trade on row d executes at close(d-1). Checking
    d instead of d-1 both misses a real unobservable execution and flags an
    observable one, depending on which side of the gap it falls. The entry
    trade's whole size is the target weight (weight_prev=0), so "fully flagged"
    means traded_missing_execution_return == traded exactly, whatever the
    target weight. (Round 4: renamed from traded_without_return -- it checks
    return availability at the execution date, nothing about price or status.)"""
    def entry(day1_ret, day2_ret):
        # A third day, still well inside the hold window, keeps the terminal
        # liquidation charge off row 1 -- it would otherwise add a second,
        # unrelated trade component to the very row under test.
        panel = pd.DataFrame([
            dict(permno=1, date=pd.Timestamp("2020-01-01"), tdi=0, ret=day1_ret,
                 value_weighted_market_return=0.0, delisting_flag="N"),
            dict(permno=1, date=pd.Timestamp("2020-01-02"), tdi=1, ret=day2_ret,
                 value_weighted_market_return=0.0, delisting_flag="N"),
            dict(permno=1, date=pd.Timestamp("2020-01-03"), tdi=2, ret=0.0,
                 value_weighted_market_return=0.0, delisting_flag="N"),
        ])
        con = duckdb.connect()
        con.register("panel", panel)
        con.register("cohort", pd.DataFrame({"permno": [1], "tdi": [0], "w": [1.0]}))
        book = daily_book(con, "panel", "2020-01-01", "2020-01-03", hold=5)
        row = book.set_index("tdi").loc[1]
        return row.traded, row.traded_missing_execution_return

    traded, flagged = entry(np.nan, 0.01)     # day 1 (execution day) unobserved
    assert traded > 0 and abs(flagged - traded) < 1e-12       # fully flagged

    traded, flagged = entry(0.01, np.nan)     # day 1 observed, despite day 2 NaN
    assert traded > 0 and flagged < 1e-9                      # not flagged at all


def test_factor_names_ignore_foreign_flags():
    """Item 4: `--from-step 6` on sys.argv must not become a factor name."""
    assert factor_names(["--from-step", "6"])[:1] == ["mom_120_20"]
    assert factor_names(["--from-step", "6"], names=["rev_5"]) == ["rev_5"]
    assert factor_names(["rev_5", "dd_252"]) == ["rev_5", "dd_252"]


def test_replay_with_external_targets_writes_next_to_them(tmp_path):
    """Item 5: corrected replay never writes into reports/week6."""
    targets = tmp_path / "replay_targets.json"
    targets.write_text("{}")
    assert replay_out_dir(str(targets)) == tmp_path.resolve()
    assert replay_out_dir(None) == W6_OUT
