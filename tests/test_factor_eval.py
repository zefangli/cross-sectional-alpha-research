import duckdb
import numpy as np
import pandas as pd

from src.evaluation.factor_eval import newey_west_tstat, performance, portfolio
from src.features.factors import ALL_FACTORS, factor_query

DAYS, TARGET = 400, 350


def frame(days=DAYS, seed=0):
    """A single stock's daily panel, with a market return it loads on."""
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0004, 0.009, days)
    return pd.DataFrame({
        "permno": 1,
        "date": pd.bdate_range("2015-01-01", periods=days),
        "ret": 0.0003 + 1.25 * market + rng.normal(0, 0.007, days),
        "value_weighted_market_return": market,
        "volume": 1_000_000.0,
        "shares_outstanding": 50_000.0,
        "eligibility_flag": True,
        "forward_return_20d": 0.0,
    })


def factor(df, name):
    """Factor series for the stock under test, indexed by row position.

    A filler stock holds the trading calendar complete, so that dropping a row
    from the stock under test creates a genuine per-stock gap.
    """
    con = duckdb.connect()
    filler = frame(seed=1).assign(permno=2)      # independent of df, so a row
    con.register("src", pd.concat([df, filler],  # dropped from df is a real gap
                                  ignore_index=True))
    out = con.sql(factor_query("src", name)).df().sort_values("date")
    return out[out.permno == 1].f.reset_index(drop=True)


# --- 5.1 medium-term momentum ------------------------------------------------

def test_momentum_compounds_the_window_from_t_minus_120_to_t_minus_21():
    df = frame()
    df["ret"] = 0.01
    assert abs(factor(df, "mom_120_20")[TARGET] - (1.01 ** 100 - 1)) < 1e-12


def test_momentum_ignores_the_skipped_recent_month():
    df = frame()
    df["ret"] = 0.01
    baseline = factor(df, "mom_120_20")[TARGET]
    df.loc[TARGET - 20:TARGET, "ret"] = 5.0
    assert factor(df, "mom_120_20")[TARGET] == baseline


def test_momentum_is_missing_when_the_window_has_a_gap_or_too_little_history():
    df = frame()
    gapped = factor(df.drop(index=TARGET - 60), "mom_120_20")
    assert pd.isna(gapped[TARGET - 1])            # positions shift by the dropped row
    assert pd.isna(factor(df, "mom_120_20")[119])


# --- 5.2 short-term reversal -------------------------------------------------

def test_reversal_negates_the_sum_of_the_last_five_returns():
    df = frame()
    df["ret"] = 0.01
    values = factor(df, "rev_5")
    assert abs(values[TARGET] - -0.05) < 1e-12
    df.loc[TARGET, "ret"] = 9.0                   # today is not part of the window
    assert factor(df, "rev_5")[TARGET] == values[TARGET]


# --- 5.3 realised volatility -------------------------------------------------

def test_realised_volatility_is_the_root_sum_of_squared_returns():
    df = frame()
    df["ret"] = 0.01
    values = factor(df, "rvol_20")
    assert abs(values[TARGET] - np.sqrt(20 * 0.01 ** 2)) < 1e-12
    df.loc[TARGET, "ret"] = -0.5                  # today is not part of the window
    assert factor(df, "rvol_20")[TARGET] == values[TARGET]


# --- 5.4 volume surprise -----------------------------------------------------

def test_volume_surprise_is_log_turnover_against_its_twenty_day_mean():
    df = frame()
    df.loc[TARGET, "volume"] *= 2
    assert abs(factor(df, "vs_20")[TARGET] - np.log(2)) < 1e-12


def test_volume_surprise_survives_a_share_split():
    """Volume and shares outstanding are as-traded in this export, so a split
    multiplies both. Turnover must be unaffected; raw share volume would not be."""
    df = frame()
    baseline = factor(df, "vs_20")[TARGET]
    split = df.copy()
    split.loc[TARGET - 3:, ["volume", "shares_outstanding"]] *= 7
    assert abs(factor(split, "vs_20")[TARGET] - baseline) < 1e-12


def test_volume_surprise_is_missing_when_the_stock_did_not_trade():
    df = frame()
    df.loc[TARGET, "volume"] = 0
    assert pd.isna(factor(df, "vs_20")[TARGET])


# --- 5.5 residual momentum ---------------------------------------------------

def test_residual_momentum_matches_an_explicit_market_model_fit():
    df = frame()
    market, ret = df.value_weighted_market_return.values, df.ret.values
    fit = slice(TARGET - 272, TARGET - 20)        # 252 rows, t-272 .. t-21
    window = slice(TARGET - 120, TARGET - 20)     # 100 rows, t-120 .. t-21
    design = np.column_stack([np.ones(252), market[fit]])
    alpha, beta = np.linalg.lstsq(design, ret[fit], rcond=None)[0]
    expected = ret[window].sum() - 100 * alpha - beta * market[window].sum()
    assert abs(factor(df, "rmom_120_20")[TARGET] - expected) < 1e-10


def test_residual_momentum_needs_the_full_estimation_window():
    df = frame()
    values = factor(df, "rmom_120_20")
    assert pd.isna(values[271])                   # one row short of t-272
    assert not pd.isna(values[272])


# --- 5.6 drawdown ------------------------------------------------------------

def test_drawdown_measures_the_fall_from_the_one_year_peak():
    df = frame()
    df["ret"] = 0.0
    df.loc[300, "ret"] = -0.10
    values = factor(df, "dd_252")
    assert abs(values[299] - 0.0) < 1e-12         # sitting at the peak
    assert abs(values[TARGET] - -0.10) < 1e-12
    assert pd.isna(values[250])                   # window not yet complete


def test_drawdown_is_measured_on_returns_not_on_the_unadjusted_price():
    """A split leaves `ret` untouched, so drawdown must not move either."""
    df = frame()
    baseline = factor(df, "dd_252")[TARGET]
    split = df.copy()
    split.loc[320:, ["volume", "shares_outstanding"]] *= 7
    assert factor(split, "dd_252")[TARGET] == baseline


# --- shared leakage guarantee ------------------------------------------------

def test_no_factor_reads_a_row_after_t():
    df = frame()
    perturbed = df.copy()
    after = perturbed.index > TARGET
    perturbed.loc[after, "ret"] *= -3
    perturbed.loc[after, "value_weighted_market_return"] *= -2
    perturbed.loc[after, ["volume", "shares_outstanding"]] *= 9
    for name in ALL_FACTORS:
        base, moved = factor(df, name)[TARGET], factor(perturbed, name)[TARGET]
        assert base == moved, name
        assert not pd.isna(base), name


# --- portfolio and statistics ------------------------------------------------

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


def test_max_drawdown_counts_a_loss_before_any_new_high():
    stats = performance(pd.Series([-0.10, 0.05]))
    assert abs(stats["max_drawdown"] - -0.10) < 1e-12


def test_newey_west_reduces_to_the_plain_t_stat_at_zero_lags():
    x = pd.Series([0.1, -0.2, 0.3, 0.05, -0.1, 0.2])
    plain = x.mean() / (x.std(ddof=0) / len(x) ** 0.5)
    assert abs(newey_west_tstat(x, 0) - plain) < 1e-12
