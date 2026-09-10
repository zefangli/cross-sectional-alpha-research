import duckdb
import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.factors import ALL_FACTORS
from src.models.splits import walk_forward_splits
from src.models.walk_forward import (
    COHORT_LAST, FEATURES, MODELS, PREDICTIONS, TARGET, WARMUP_DAYS,
    _select_ridge_alpha, fold_frames, model_specs,
)


def panel(dates, permnos=(1, 2, 3), seed=0):
    """One row per (permno, date): a dense tdi over the date axis, the six
    rank factors and the target -- everything fold_frames selects."""
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(dates).unique()))
    tdi = {d: i for i, d in enumerate(dates)}
    n = len(dates) * len(permnos)
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "permno": np.repeat(permnos, len(dates)),
        "date": np.tile(dates, len(permnos)),
    })
    frame["tdi"] = frame.date.map(tdi)
    frame["aligned"] = True
    for f in ALL_FACTORS:
        frame[f"rank_{f}"] = rng.uniform(0, 1, n)
    frame[TARGET] = rng.normal(0, 0.05, n)
    return frame


# --- fold_frames: chronology --------------------------------------------------

def test_training_rows_strictly_precede_every_validation_period():
    dates = pd.bdate_range("2020-01-01", "2022-12-31")
    frame = panel(dates)
    con = duckdb.connect()
    con.register("panel", frame)
    splits = walk_forward_splits(dates, first_validation_year=2021, last_validation_year=2022)
    assert len(splits) == 2                        # both fold years actually present
    for _, fold in splits.iterrows():
        train, predict = fold_frames(con, "panel", fold)
        assert train.date.max() < pd.Timestamp(fold.validation_start)
        assert train.date.max() < predict.loc[predict.is_validation, "date"].min()


# --- fold_frames: purge and cohort warm-up ------------------------------------

def test_predict_block_starts_exactly_warmup_days_after_train_end_and_never_leaks_into_train():
    dates = pd.bdate_range("2020-01-01", "2021-12-31")
    frame = panel(dates)
    con = duckdb.connect()
    con.register("panel", frame)
    fold = walk_forward_splits(dates, first_validation_year=2021, last_validation_year=2021).iloc[0]
    train, predict = fold_frames(con, "panel", fold)

    tdi_of = dict(zip(frame.date, frame.tdi))
    val_start_tdi = tdi_of[pd.Timestamp(fold.validation_start)]
    train_end_tdi = tdi_of[pd.Timestamp(fold.train_end)]

    assert val_start_tdi - train_end_tdi == 21                # the fold's own purge gap
    assert train.tdi.max() == train_end_tdi                   # train reaches its boundary exactly
    assert predict.tdi.min() == val_start_tdi - WARMUP_DAYS    # predict starts exactly there...
    assert predict.tdi.min() == train_end_tdi + 1              # ...the very next trading day

    warmup = predict[~predict.is_validation]
    assert len(warmup) > 0
    assert (warmup.date < pd.Timestamp(fold.validation_start)).all()          # flagged correctly
    validated = predict.loc[predict.is_validation, "date"]
    assert (validated >= pd.Timestamp(fold.validation_start)).all()

    leaked = pd.merge(train[["permno", "date"]], warmup[["permno", "date"]])
    assert leaked.empty                                        # no warm-up row ever in TRAIN


# --- fold_frames: the sealed period -------------------------------------------

def test_fold_frames_caps_the_predict_block_at_the_sealed_period():
    dates = pd.bdate_range("2020-01-01", "2025-12-31")
    frame = panel(dates)
    con = duckdb.connect()
    con.register("panel", frame)

    # A fold whose nominal validation window reaches deep into 2024-2025, as if
    # last_evaluable had never trimmed it -- fold_frames must seal it anyway.
    fold = pd.Series({
        "train_end": pd.Timestamp("2023-06-30").date(),
        "validation_start": pd.Timestamp("2023-07-31").date(),
        "validation_end": pd.Timestamp("2025-06-30").date(),
    })
    train, predict = fold_frames(con, "panel", fold)

    assert train.date.max() < pd.Timestamp("2024-01-01")
    assert predict.date.max() <= pd.Timestamp(COHORT_LAST)
    assert predict.date.max() < pd.Timestamp("2024-01-01")


def test_generated_predictions_never_reach_the_sealed_period():
    if not PREDICTIONS.exists():
        pytest.skip("week4_predictions.parquet not generated yet")
    dates = pd.read_parquet(PREDICTIONS, columns=["date"]).date
    assert dates.max() <= pd.Timestamp(COHORT_LAST)


# --- preprocessing and tuning stay inside TRAIN -------------------------------

def test_model_specs_return_pipelines_with_an_unfitted_scaler():
    for name in MODELS:
        pipeline = model_specs()[name]()
        assert isinstance(pipeline, Pipeline)
        scaler = pipeline.named_steps["scaler"]
        assert isinstance(scaler, StandardScaler)
        assert not hasattr(scaler, "mean_")            # never fit yet


def test_predicting_a_shifted_distribution_does_not_move_the_fitted_scaler():
    train = panel(pd.bdate_range("2020-01-01", "2020-06-30"), permnos=(1, 2))
    pipeline = model_specs()["ols"]()
    pipeline.fit(train[FEATURES], train[TARGET])
    scaler = pipeline.named_steps["scaler"]
    mean_after_fit, scale_after_fit = scaler.mean_.copy(), scaler.scale_.copy()

    weird = train.copy()
    weird[FEATURES] = weird[FEATURES] * 1000 + 500     # wildly different distribution
    pipeline.predict(weird[FEATURES])

    assert np.array_equal(scaler.mean_, mean_after_fit)
    assert np.array_equal(scaler.scale_, scale_after_fit)      # predict never re-fits


def test_ridge_inner_search_ignores_the_purged_gap():
    train = panel(pd.bdate_range("2020-01-01", "2020-12-31"), permnos=(1, 2, 3), seed=1)
    baseline_alpha = _select_ridge_alpha(train)

    unique_dates = np.sort(train.date.unique())
    val_start_idx = int(len(unique_dates) * 0.8)
    train_end_idx = val_start_idx - WARMUP_DAYS - 1
    purge_dates = unique_dates[train_end_idx + 1: val_start_idx]
    assert len(purge_dates) == WARMUP_DAYS             # sanity: the module's own gap

    corrupted = train.copy()
    corrupted.loc[corrupted.date.isin(purge_dates), TARGET] = 999.0
    assert _select_ridge_alpha(corrupted) == baseline_alpha
