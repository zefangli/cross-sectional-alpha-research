import duckdb
import numpy as np
import pandas as pd

from src.features.exposures import exposures_query, sic_interval_query

DAYS, TARGET = 400, 350


def panel_frame(days=DAYS, seed=0, beta=0.7):
    """A single stock's daily panel, with a market return it loads on."""
    rng = np.random.default_rng(seed)
    market = rng.normal(0.0004, 0.009, days)
    return pd.DataFrame({
        "permno": 1,
        "date": pd.bdate_range("2015-01-01", periods=days),
        "ret": 0.0003 + beta * market,
        "value_weighted_market_return": market,
        "market_cap": 1_000_000.0,
    })


def sic_frame(rows):
    """rows: (start, end, siccd) tuples for a single PERMNO. The header row
    (`SecurityHdrFlg='Y'`) is always the FIRST interval, matching the real
    export, so a test that reads the header row instead of the interval
    containing the date would get the wrong answer for later dates."""
    return pd.DataFrame({
        "PERMNO": [1] * len(rows),
        "SecInfoStartDt": [r[0] for r in rows],
        "SecInfoEndDt": [r[1] for r in rows],
        "SICCD": [r[2] for r in rows],
        "SecurityHdrFlg": ["Y"] + ["N"] * (len(rows) - 1),
    })


def build(panel, sic_rows):
    con = duckdb.connect()
    con.register("sic_raw", sic_rows)
    sic = con.sql(sic_interval_query("sic_raw")).df()
    con.register("panel", panel)
    con.register("sic", sic)
    return con.sql(exposures_query("panel", "sic")).df().sort_values("date").reset_index(drop=True)


# --- sector --------------------------------------------------------------

def test_sector_comes_from_the_interval_containing_the_date_not_the_header_row():
    boundary = pd.bdate_range("2015-01-01", periods=DAYS)[200]
    sic_rows = sic_frame([
        ("2000-01-01", str((boundary - pd.Timedelta(days=1)).date()), "1000"),  # header row
        (str(boundary.date()), "2099-12-31", "7000"),
    ])
    out = build(panel_frame(), sic_rows)
    assert out.sector.iloc[100] == 2    # well before the change: mining
    assert out.sector.iloc[300] == 9    # well after: services, not the header's mining


def test_a_sentinel_sic_code_carries_the_prior_interval_forward_never_a_later_one():
    sic_rows = sic_frame([
        ("2000-01-01", "2010-12-31", "1000"),  # mining
        ("2011-01-01", "2011-12-31", "0"),     # sentinel
        ("2012-01-01", "2099-12-31", "7000"),  # services
    ])
    con = duckdb.connect()
    con.register("sic_raw", sic_rows)
    filled = con.sql(sic_interval_query("sic_raw")).df().sort_values("start_date").reset_index(drop=True)
    assert filled.sector.iloc[1] == 2       # carried from the prior interval, not the later one
    assert filled.carried_forward.iloc[1]


# --- beta_252 --------------------------------------------------------------

def test_beta_252_recovers_a_known_loading():
    market = np.linspace(-0.02, 0.02, DAYS)
    panel = pd.DataFrame({
        "permno": 1,
        "date": pd.bdate_range("2015-01-01", periods=DAYS),
        "ret": 0.7 * market,
        "value_weighted_market_return": market,
        "market_cap": 1_000_000.0,
    })
    sic_rows = sic_frame([("2000-01-01", "2099-12-31", "7000")])
    out = build(panel, sic_rows)
    assert abs(out.beta_252.iloc[300] - 0.7) < 1e-9


# --- log_mcap ----------------------------------------------------------------

def test_log_mcap_is_null_not_negative_infinity_for_a_non_positive_market_cap():
    panel = panel_frame()
    panel.loc[TARGET, "market_cap"] = 0.0
    sic_rows = sic_frame([("2000-01-01", "2099-12-31", "7000")])
    out = build(panel, sic_rows)
    lookback = out.log_mcap.iloc[TARGET + 1]        # t-1 lookup sees the zero cap
    assert pd.isna(lookback)                        # NULL, not -inf, and no exception raised


# --- shared leakage guarantee ------------------------------------------------

def test_no_exposure_reads_a_row_at_or_after_t():
    """Every exposure must be determined by the close of t-1, the same rule
    every factor obeys. Perturbing the daily inputs and the sector assignment
    on or after t must not move sector, beta_252 or log_mcap at t."""
    panel = panel_frame()
    boundary = panel.date.iloc[TARGET]
    before_end = str((boundary - pd.Timedelta(days=1)).date())
    base = build(panel, sic_frame([
        ("2000-01-01", before_end, "1000"),
        (str(boundary.date()), "2099-12-31", "7000"),
    ]))

    perturbed = panel.copy()
    after = perturbed.index >= TARGET
    perturbed.loc[after, "ret"] *= -3
    perturbed.loc[after, "value_weighted_market_return"] *= -2
    perturbed.loc[after, "market_cap"] *= 9
    moved = build(perturbed, sic_frame([
        ("2000-01-01", before_end, "1000"),
        (str(boundary.date()), "2199-12-31", "9100"),  # different sector and end date, both >= t
    ]))

    for col in ("sector", "beta_252", "log_mcap"):
        b, m = base[col].iloc[TARGET], moved[col].iloc[TARGET]
        assert b == m, col
        assert not pd.isna(b), col
