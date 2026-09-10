import numpy as np
import pandas as pd

from src.evaluation.week5_neutral import neutralise, residualize


def exposure_frame(n_per_date=200, n_dates=3, sector_range=5, seed=0, degenerate_date=None):
    """One cross-section per date: sector, winsorised beta and log market cap.

    `degenerate_date` optionally forces one row on a given date index to carry
    a sector code no other row that date has -- a single-member sector, the
    edge case the design must survive without raising or producing NaN.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    rows = []
    for i, d in enumerate(dates):
        sector = rng.integers(0, sector_range, n_per_date)
        if degenerate_date == i:
            sector[0] = sector_range + 5   # a code unique to this one row
        rows.append(pd.DataFrame({
            "permno": np.arange(n_per_date), "date": d, "tdi": i,
            "sector": sector,
            "beta_252_w": rng.normal(0, 1, n_per_date),
            "log_mcap_w": rng.normal(10, 1, n_per_date),
        }))
    return pd.concat(rows, ignore_index=True)


# --- residualize: recovers zero signal from an exact linear function --------

def test_residual_is_near_zero_when_score_is_an_exact_linear_function_of_the_exposures():
    frame = exposure_frame()
    sector_effect = {s: (-1) ** s * s for s in range(5)}
    frame["score"] = (frame.sector.map(sector_effect)
                       + 2.0 * frame.beta_252_w - 0.5 * frame.log_mcap_w)
    residual = residualize(frame)
    assert np.abs(residual).max() < 1e-8


# --- residualize: orthogonality -----------------------------------------------

def test_residual_is_orthogonal_to_each_exposure_within_every_date():
    frame = exposure_frame(seed=2)
    rng = np.random.default_rng(3)
    frame["score"] = rng.normal(0, 1, len(frame))     # no linear relationship to strip
    frame["residual"] = residualize(frame)
    for _, g in frame.groupby("date"):
        assert abs(np.dot(g.residual, g.beta_252_w)) < 1e-8
        assert abs(np.dot(g.residual, g.log_mcap_w)) < 1e-8
        # Sector dummies are one-hot: orthogonality to each dummy is exactly
        # the residual having zero mean within that sector.
        sector_means = g.groupby("sector").residual.mean()
        assert sector_means.abs().max() < 1e-8


# --- residualize: degenerate sector never raises or produces NaN -------------

def test_a_single_member_sector_does_not_raise_or_produce_nan():
    frame = exposure_frame(seed=4, degenerate_date=0)
    rng = np.random.default_rng(5)
    frame["score"] = rng.normal(0, 1, len(frame))
    residual = residualize(frame)      # must not raise
    assert np.isfinite(residual).all()
    assert not np.isnan(residual).any()


def test_a_sector_absent_from_a_date_does_not_raise_or_produce_nan():
    """`sector_0`, the real catch-all, is absent from most dates in the real
    panel; every other sector code can be absent on a given date too."""
    frame = exposure_frame(n_per_date=30, sector_range=3, seed=6)   # only 0..2 ever appear
    rng = np.random.default_rng(7)
    frame["score"] = rng.normal(0, 1, len(frame))
    residual = residualize(frame)
    assert np.isfinite(residual).all()


# --- neutralise: end-to-end shape --------------------------------------------

def test_neutralise_ranks_the_residual_into_a_valid_decile_book():
    exposures = exposure_frame(seed=8)
    rng = np.random.default_rng(9)
    score_frame = exposures[["permno", "date", "tdi"]].copy()
    score_frame["score"] = rng.normal(0, 1, len(exposures))

    out = neutralise(score_frame, exposures)
    assert set(out.columns) == {"permno", "date", "tdi", "rank", "decile"}
    assert not out[["rank", "decile"]].isna().any().any()
    assert out["rank"].between(0, 1).all()
    assert set(out["decile"].unique()) <= {-1.0, 0.0, 1.0}
    for _, g in out.groupby("date"):
        # pandas' `rank(pct=True)` reports rank/count, so the minimum is
        # 1/count, not 0 -- the same convention `book_frame`'s own decile
        # bucketing relies on throughout the codebase.
        assert np.isclose(g["rank"].min(), 1.0 / len(g))
        assert np.isclose(g["rank"].max(), 1.0)


def test_neutralise_removes_a_pure_beta_tilt_leaving_only_independent_signal():
    """A score dominated by a `beta_252_w` tilt (coefficient 5, versus
    independent noise of unit scale) should have that tilt fully absorbed by
    the regression, since `beta_252_w` is literally one of the regressors --
    the neutralised rank should then no longer correlate with the raw beta
    that was purged, only with what was independent of it."""
    exposures = exposure_frame(n_per_date=500, n_dates=2, seed=10)
    rng = np.random.default_rng(11)
    score_frame = exposures[["permno", "date", "tdi"]].copy()
    score_frame["score"] = 5.0 * exposures["beta_252_w"] + rng.normal(0, 1, len(exposures))

    out = neutralise(score_frame, exposures).merge(
        exposures[["permno", "date", "tdi", "beta_252_w"]], on=["permno", "date", "tdi"])
    corr_by_date = out.groupby("date").apply(
        lambda g: np.corrcoef(g["rank"], g["beta_252_w"])[0, 1])
    assert corr_by_date.abs().max() < 0.1
