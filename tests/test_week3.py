import duckdb
import numpy as np
import pandas as pd

from src.models.splits import walk_forward_splits
from src.portfolio.backtest import capped_neutral_weights, daily_book, performance_daily

HOLD = 20


def cross_section(n=100, dates=("2020-01-02", "2020-01-03")):
    return pd.DataFrame({
        "date": np.repeat(list(dates), n),
        "signal": np.tile(np.linspace(0, 1, n), len(dates)),
    })


# --- weight construction -----------------------------------------------------

def test_weights_are_market_neutral_and_unit_gross():
    frame = cross_section(n=400)                 # wide enough that the cap is slack
    w = capped_neutral_weights(frame, "signal")
    by_date = w.groupby(frame.date)
    assert by_date.sum().abs().max() < 1e-12
    assert (by_date.apply(lambda s: s.abs().sum()) - 1).abs().max() < 1e-12


def test_weights_are_monotone_in_the_signal():
    frame = cross_section(n=11, dates=("2020-01-02",))
    w = capped_neutral_weights(frame, "signal", cap=1.0)
    assert (w.diff().dropna() > 0).all()
    assert w.iloc[0] < 0 < w.iloc[-1]


def test_position_cap_binds_on_a_small_cross_section():
    frame = cross_section(n=6, dates=("2020-01-02",))
    w = capped_neutral_weights(frame, "signal", cap=0.2)
    assert w.abs().max() <= 0.2 + 1e-9           # the cap is authoritative
    assert abs(w.sum()) < 1e-12                  # still neutral after capping
    assert w.abs().sum() < 1.0                   # gross gives way, not the cap


def test_cap_does_not_bind_on_a_wide_cross_section():
    w = capped_neutral_weights(cross_section(n=1000, dates=("2020-01-02",)), "signal")
    assert w.abs().max() < 0.01


# --- walk-forward splits -----------------------------------------------------

def trading_calendar():
    return pd.bdate_range("2006-01-02", "2023-12-29")


def test_splits_purge_the_target_horizon_before_validation():
    dates = pd.Series(trading_calendar())
    splits = walk_forward_splits(dates, last_evaluable="2023-11-30")
    assert list(splits.fold) == list(range(1, 11))
    for _, fold in splits.iterrows():
        gap = dates[(dates > pd.Timestamp(fold.train_end))
                    & (dates < pd.Timestamp(fold.validation_start))]
        assert len(gap) == HOLD, fold.fold      # exactly the horizon, purged
        assert fold.train_end < fold.validation_start


def test_splits_expand_and_never_reach_past_the_seal():
    splits = walk_forward_splits(pd.Series(trading_calendar()), last_evaluable="2023-11-30")
    assert splits.train_days.is_monotonic_increasing
    assert splits.train_start.nunique() == 1
    assert str(splits.validation_end.max()) <= "2023-11-30"


# --- staggered cohorts and daily P&L -----------------------------------------

def book_for(weights, panel):
    con = duckdb.connect()
    con.register("cohort", weights)
    con.register("panel", panel)
    return daily_book(con, "panel", "2020-01-01", "2030-01-01")


def flat_panel(days=60, ret=0.0):
    """Two stocks, contiguous trading-day index, constant daily return."""
    return pd.DataFrame({
        "permno": np.repeat([1, 2], days),
        "date": np.tile(pd.bdate_range("2020-01-01", periods=days), 2),
        "tdi": np.tile(np.arange(days), 2),
        "ret": ret,
        "value_weighted_market_return": 0.0,
    })


def test_a_single_cohort_is_held_for_exactly_twenty_days():
    panel = flat_panel()
    weights = pd.DataFrame({"permno": [1, 2], "tdi": [10, 10], "w": [1.0, -1.0]})
    book = book_for(weights, panel).set_index("tdi")
    assert book.gross_exposure.loc[11:30].round(12).eq(2.0 / HOLD).all()
    assert 31 not in book.index or book.gross_exposure.loc[31] == 0
    assert 10 not in book.index                  # nothing held on the formation day


def test_twenty_stacked_cohorts_reach_full_gross_exposure():
    panel = flat_panel()
    weights = pd.DataFrame({
        "permno": np.repeat([1, 2], 20), "tdi": np.tile(np.arange(20), 2),
        "w": [0.5] * 20 + [-0.5] * 20,
    })
    book = book_for(weights, panel).set_index("tdi")
    assert abs(book.gross_exposure.loc[20] - 1.0) < 1e-12
    assert abs(book.net_exposure.loc[20]) < 1e-12


def test_daily_pnl_marks_weights_against_that_days_return():
    panel = flat_panel(ret=0.01)
    panel.loc[panel.permno == 2, "ret"] = -0.01
    weights = pd.DataFrame({"permno": [1, 2], "tdi": [10, 10], "w": [1.0, -1.0]})
    book = book_for(weights, panel).set_index("tdi")
    # +1/20 on a +1% stock and -1/20 on a -1% stock
    assert abs(book.gross_return.loc[11] - 2 * 0.01 / HOLD) < 1e-12


def test_turnover_counts_the_cohort_entering_and_the_cohort_expiring():
    panel = flat_panel()
    weights = pd.DataFrame({"permno": [1], "tdi": [10], "w": [1.0]})
    book = book_for(weights, panel).set_index("tdi")
    assert abs(book.traded.loc[11] - 1.0 / HOLD) < 1e-12   # entry
    assert abs(book.traded.loc[31] - 1.0 / HOLD) < 1e-12   # expiry
    assert book.traded.loc[12:30].abs().max() < 1e-12      # nothing in between


def test_a_gap_in_a_stocks_history_does_not_extend_its_holding():
    panel = flat_panel()
    panel = panel[~((panel.permno == 1) & (panel.tdi.between(15, 17)))]
    weights = pd.DataFrame({"permno": [1], "tdi": [10], "w": [1.0]})
    book = book_for(weights, panel).set_index("tdi")
    assert abs(book.gross_exposure.loc[14] - 1.0 / HOLD) < 1e-12
    assert abs(book.gross_exposure.loc[18] - 1.0 / HOLD) < 1e-12   # resumes by date
    assert 31 not in book.index or book.gross_exposure.loc[31] == 0


# --- statistics --------------------------------------------------------------

def test_market_beta_recovers_a_known_loading():
    market = pd.Series(np.linspace(-0.02, 0.02, 200))
    stats = performance_daily(0.7 * market, market)
    assert abs(stats["market_beta"] - 0.7) < 1e-9
