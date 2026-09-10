import duckdb
import numpy as np
import pandas as pd
import pytest

from src.evaluation.week6_final import (REPLAY_PNL_LAST, main, neutral_exposures,
                                        resolve_factors, resolve_name, score_frame, validate_spec)
from src.features.factors import ALL_FACTORS, FACTOR_SIGN
from src.portfolio.backtest import capped_neutral_weights

NEUTRALISATION_BLOCK = {
    "regressors": ["sector dummies (10 of 11 SIC divisions; sector_0 dropped)",
                   "beta_252 (cross-sectionally winsorised)", "log_mcap (cross-sectionally winsorised)"],
    "winsorise_quantiles": [0.01, 0.99],
}


def factor_entries(names):
    return [{"name": f, "sign": FACTOR_SIGN[f]} for f in names]


def base_spec(**overrides):
    spec = {
        "git_commit": "deadbeef", "locked_book": "composite__neutral__decile",
        "weighting": "decile", "neutralised": True, "factor_set": "all six",
        "factors": factor_entries(ALL_FACTORS), "hold_days": 20, "cap": 0.01,
        "neutralisation": NEUTRALISATION_BLOCK,
        "realised_beta": -0.05, "net_sharpe_10bp": 0.2, "gross_sharpe": 0.48,
    }
    spec.update(overrides)
    return spec


def synthetic_scan(con, n_dates=4, n_per_date=80, seed=0):
    """A factor_panel-like table plus an exposures-like table over the same
    (permno, date, tdi) keys. `rank_mom_120_20` is set to the within-date
    percentile rank of `beta_252` (mom_120_20's sign is +1), so the raw
    composite score carries a genuine beta tilt that a working neutralisation
    must strip out; the other five factor ranks are independent noise."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    panel_rows, exp_rows = [], []
    for i, d in enumerate(dates):
        beta = rng.normal(0, 1, n_per_date)
        beta_rank = pd.Series(beta).rank(pct=True).to_numpy()
        sector = rng.integers(0, 5, n_per_date)
        mcap = rng.normal(10, 1, n_per_date)
        for p in range(n_per_date):
            row = {"permno": p, "date": d, "tdi": i, "aligned": True,
                   "ret": rng.normal(0, 0.01), "value_weighted_market_return": rng.normal(0, 0.01),
                   "forward_return_20d": rng.normal(0, 0.05), "rank_mom_120_20": beta_rank[p]}
            for f in ALL_FACTORS:
                if f != "mom_120_20":
                    row[f"rank_{f}"] = rng.uniform(0, 1)
            panel_rows.append(row)
            exp_rows.append({"permno": p, "date": d, "tdi": i, "sector": int(sector[p]),
                             "beta_252": beta[p], "log_mcap": mcap[p]})
    con.register("factor_panel", pd.DataFrame(panel_rows))
    con.register("exposures", pd.DataFrame(exp_rows))
    return "factor_panel", "exposures", dates


# --- validate_spec: required fields and the commit guard ---------------------

def test_validate_spec_refuses_when_a_required_field_is_missing():
    spec = base_spec()
    del spec["cap"]
    with pytest.raises(ValueError):
        validate_spec(spec, head_commit="deadbeef")


def test_validate_spec_refuses_when_the_recorded_commit_does_not_match_head():
    spec = base_spec(git_commit="deadbeef")
    with pytest.raises(ValueError):
        validate_spec(spec, head_commit="a-different-commit")


def test_validate_spec_accepts_a_complete_spec_whose_commit_matches_head():
    spec = base_spec(git_commit="deadbeef")
    assert validate_spec(spec, head_commit="deadbeef") is spec


def test_validate_spec_refuses_a_factor_sign_that_disagrees_with_the_pre_registered_sign():
    spec = base_spec(factors=[{"name": "mom_120_20", "sign": -1}])   # pre-registered sign is +1
    with pytest.raises(ValueError):
        validate_spec(spec, head_commit="deadbeef")


# --- resolve_name: composite-family scope, not fitted models -----------------

def test_resolve_name_refuses_a_fitted_model_specification():
    with pytest.raises(ValueError):
        resolve_name(base_spec(locked_book="ols__neutral__decile"))


def test_resolve_name_accepts_composite_regardless_of_suffix_order():
    assert resolve_name(base_spec(locked_book="composite__decile__neutral")) == "composite"
    assert resolve_name(base_spec(locked_book="composite__neutral__decile")) == "composite"


def test_resolve_name_accepts_an_ablated_composite_label():
    assert resolve_name(base_spec(locked_book="drop_rmom_120_20__neutral__decile")) == "drop_rmom_120_20"


# --- resolve_factors: names, and a sign cross-check against factors.py -------

def test_resolve_factors_accepts_an_ablated_list_of_factor_names():
    ablated = [f for f in ALL_FACTORS if f != "rev_5"]
    assert resolve_factors(base_spec(factors=factor_entries(ablated))) == tuple(ablated)


# --- the sealed-period guard is structural, not a comment --------------------

def test_running_without_the_sealed_opt_in_never_reads_a_date_after_2023_12_29():
    assert pd.Timestamp(REPLAY_PNL_LAST) <= pd.Timestamp("2023-12-29")
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["bogus-flag"])


# --- weighting and neutralisation match the spec ------------------------------

def test_flipping_weighting_in_the_spec_changes_the_weights_produced():
    con = duckdb.connect()
    scan, exp_scan, dates = synthetic_scan(con, seed=2)
    first, last = str(dates.min().date()), str(dates.max().date())
    spec = base_spec(neutralised=False)
    frame = score_frame(con, scan, exp_scan, spec, first, last)
    rank_w = capped_neutral_weights(frame, "rank")
    decile_w = capped_neutral_weights(frame, "decile")
    assert not np.allclose(rank_w.to_numpy(), decile_w.to_numpy())
    assert rank_w.nunique() > decile_w.nunique()


def test_neutralised_score_correlates_less_with_beta_than_the_raw_score_does():
    con = duckdb.connect()
    scan, exp_scan, dates = synthetic_scan(con, seed=3)
    first, last = str(dates.min().date()), str(dates.max().date())
    raw = score_frame(con, scan, exp_scan, base_spec(neutralised=False), first, last)
    neutral = score_frame(con, scan, exp_scan, base_spec(neutralised=True), first, last)
    exposures = neutral_exposures(con, scan, exp_scan, first, last)

    def mean_abs_corr(frame):
        merged = frame.merge(exposures, on=["permno", "date", "tdi"])
        return merged.groupby("date").apply(
            lambda g: abs(np.corrcoef(g["rank"], g["beta_252_w"])[0, 1])).mean()

    assert mean_abs_corr(neutral) < mean_abs_corr(raw)
