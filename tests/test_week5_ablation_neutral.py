import numpy as np
import pandas as pd

from src.evaluation.week5_ablation_neutral import dropped_composite
from src.features.factors import ALL_FACTORS, FACTOR_SIGN


def raw_frame(seed=0, n=50):
    """One cross-section carrying a `rank_<factor>` column for each of the six factors."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({"permno": np.arange(n), "date": pd.Timestamp("2020-01-02"), "tdi": 0})
    for f in ALL_FACTORS:
        frame[f"rank_{f}"] = rng.uniform(0, 1, n)
    return frame


# --- dropped_composite: drops exactly the intended factor --------------------

def test_dropped_composite_equals_the_signed_average_of_exactly_the_five_kept_factors():
    frame = raw_frame()
    dropped = "rvol_20"
    kept = [f for f in ALL_FACTORS if f != dropped]
    expected = sum(FACTOR_SIGN[f] * frame[f"rank_{f}"] for f in kept) / len(kept)
    actual = dropped_composite(frame, dropped)["rank"]
    assert np.allclose(actual.to_numpy(), expected.to_numpy())


def test_dropped_composite_is_unaffected_by_changes_to_the_dropped_factors_own_rank():
    frame = raw_frame()
    dropped = "rmom_120_20"
    baseline = dropped_composite(frame, dropped)["rank"].to_numpy()
    frame[f"rank_{dropped}"] = 1 - frame[f"rank_{dropped}"]
    perturbed = dropped_composite(frame, dropped)["rank"].to_numpy()
    assert np.allclose(baseline, perturbed)
