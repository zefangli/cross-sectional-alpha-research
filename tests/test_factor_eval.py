from datetime import date, timedelta

import duckdb
import pandas as pd

from src.evaluation.factor_eval import newey_west_tstat, portfolio
from src.features.factors import factor_query

DAYS, WINDOW_START, WINDOW_END, TARGET = 150, 120, 21, 130


def day(i):
    return date(2020, 1, 1) + timedelta(days=i)


def source_rows(ret=0.01, overrides=None, drop=None):
    """Panel for the stock under test, plus a filler stock that holds the calendar
    complete so that dropping a row creates a genuine per-stock gap."""
    overrides = overrides or {}
    tested = [(1, day(i), overrides.get(i, ret), True, 0.0)
              for i in range(DAYS) if i != drop]
    filler = [(2, day(i), ret, True, 0.0) for i in range(DAYS)]
    return tested + filler


def factor(rows, name="mom_120_20"):
    con = duckdb.connect()
    con.execute("CREATE TABLE src (permno BIGINT, date DATE, ret DOUBLE, "
                "eligibility_flag BOOLEAN, forward_return_20d DOUBLE)")
    con.executemany("INSERT INTO src VALUES (?, ?, ?, ?, ?)", rows)
    values = con.sql(factor_query("src", name)).df()
    values = values[values.permno == 1]
    return values.set_index(values.date.dt.date).f


def test_momentum_compounds_the_window_from_t_minus_120_to_t_minus_21():
    assert abs(factor(source_rows())[day(TARGET)] - (1.01 ** 100 - 1)) < 1e-12


def test_momentum_ignores_the_skipped_recent_month_and_all_future_rows():
    baseline = factor(source_rows())[day(TARGET)]
    skipped = {i: 5.0 for i in range(TARGET - WINDOW_END + 1, TARGET + 1)}
    future = {i: 5.0 for i in range(TARGET + 1, DAYS)}
    assert factor(source_rows(overrides=skipped))[day(TARGET)] == baseline
    assert factor(source_rows(overrides=future))[day(TARGET)] == baseline
    # sanity: a change *inside* the window must move the factor
    assert factor(source_rows(overrides={TARGET - WINDOW_START: 0.5}))[day(TARGET)] != baseline


def test_momentum_is_missing_when_the_window_has_a_gap_or_too_little_history():
    assert pd.isna(factor(source_rows(drop=TARGET - 60))[day(TARGET)])
    assert pd.isna(factor(source_rows())[day(WINDOW_START - 1)])


def test_turnover_counts_exits_and_costs_scale_with_traded_notional():
    weights = pd.DataFrame({
        "date": ["d1", "d1", "d2", "d2"],
        "permno": [1, 2, 1, 3],
        "w": [1.0, -1.0, 1.0, -1.0],
        "y": [0.10, -0.05, 0.0, 0.0],
    })
    book = portfolio(weights)
    assert abs(book.gross_return.iloc[0] - 0.15) < 1e-12
    assert book.turnover.tolist() == [1.0, 1.0]      # build, then a one-name swap
    assert abs(book.net_return_10bp.iloc[0] - (0.15 - 0.0010 * 2)) < 1e-12


def test_newey_west_reduces_to_the_plain_t_stat_at_zero_lags():
    x = pd.Series([0.1, -0.2, 0.3, 0.05, -0.1, 0.2])
    plain = x.mean() / (x.std(ddof=0) / len(x) ** 0.5)
    assert abs(newey_west_tstat(x, 0) - plain) < 1e-12
