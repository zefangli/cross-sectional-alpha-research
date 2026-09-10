"""Week 4: OLS, Ridge and gradient boosting over the ten Week 3 folds.

Same six rank factors and the same walk-forward folds as Week 3 -- only the
signal changes, from an equal-weighted composite of signed ranks to a fitted
model. Ridge and gradient boosting can weight `rev_5` and `vs_20` above the
other four, which Week 3 found to be the only factors independent of the
momentum/volatility cluster; that is the mechanism by which either could beat
the composite's 0.147 gross Sharpe bar.

Every model is fit on TRAIN rows only (aligned, date <= fold.train_end, target
not null) and scored on a PREDICT block that starts `WARMUP_DAYS` trading days
before validation_start -- exactly the fold's own purge gap -- so the 20
staggered daily cohorts a downstream backtest would form are already fully
ramped on the first scored validation day. Warm-up rows are flagged
`is_validation = False` and are never part of TRAIN.

Gradient boosting uses HistGradientBoostingRegressor, not LightGBM: LightGBM
is not installed and won't be added for one model, and this is the same
histogram-boosting algorithm already shipped with an existing dependency.

2024-2025 stays sealed: COHORT_LAST caps every date this module reads.
"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.factors import ALL_FACTORS
from src.models.splits import walk_forward_splits

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "processed" / "factor_panel"
PREDICTIONS = ROOT / "data" / "processed" / "week4_predictions.parquet"
OUT = ROOT / "reports" / "week4"

FEATURES = [f"rank_{f}" for f in ALL_FACTORS]
TARGET = "forward_return_20d"
COHORT_LAST = "2023-11-30"   # last formation date whose 20-day hold ends in 2023
WARMUP_DAYS = 20
MODELS = ("ols", "ridge", "gbm")

RIDGE_ALPHAS = np.logspace(-2, 4, 7)
GBM_PARAMS = dict(max_iter=200, learning_rate=0.05, max_depth=4,
                  min_samples_leaf=200, early_stopping=False, random_state=0)


def model_specs() -> dict:
    """Zero-arg factories, one per name in MODELS.

    Scaling lives inside the pipeline so it structurally can only ever see
    training rows; on ranks already in [0,1] it changes little, but the guard
    is free.
    """
    return {
        "ols": lambda: Pipeline([("scaler", StandardScaler()), ("model", LinearRegression())]),
        "ridge": lambda: Pipeline([("scaler", StandardScaler()), ("model", Ridge())]),
        "gbm": lambda: Pipeline([("scaler", StandardScaler()),
                                 ("model", HistGradientBoostingRegressor(**GBM_PARAMS))]),
    }


def _select_ridge_alpha(train: pd.DataFrame) -> float:
    """Best alpha by inner-validation MSE on a purged chronological split of
    `train`'s own dates: the last ~20% of dates held out, 20 trading days
    purged before them, exactly as the outer folds do.
    """
    dates = np.sort(train["date"].unique())
    val_start_idx = int(len(dates) * 0.8)
    train_end_idx = val_start_idx - WARMUP_DAYS - 1
    if train_end_idx < 0:                       # negative would wrap, not raise
        raise ValueError(f"{len(dates)} training dates is too few to purge an inner split")
    inner_train = train[train.date <= dates[train_end_idx]]
    inner_val = train[train.date >= dates[val_start_idx]]
    best_alpha, best_mse = RIDGE_ALPHAS[0], np.inf
    for alpha in RIDGE_ALPHAS:
        pipeline = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=alpha))])
        pipeline.fit(inner_train[FEATURES], inner_train[TARGET])
        mse = mean_squared_error(inner_val[TARGET], pipeline.predict(inner_val[FEATURES]))
        if mse < best_mse:
            best_alpha, best_mse = alpha, mse
    return float(best_alpha)


def fit_predict(train: pd.DataFrame, predict_frame: pd.DataFrame, name: str) -> np.ndarray:
    """Fit `name` on `train` rows only, predict `predict_frame` rows.

    Ridge picks its alpha from `_select_ridge_alpha` before refitting on all of
    `train`; the chosen value is stashed on this function so `main` can log it
    without re-running the inner search just for reporting.
    """
    if name == "ridge":
        alpha = _select_ridge_alpha(train)
        pipeline = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=alpha))])
        fit_predict.last_alpha = alpha
    else:
        pipeline = model_specs()[name]()
    pipeline.fit(train[FEATURES], train[TARGET])
    return pipeline.predict(predict_frame[FEATURES]).astype(np.float32)


fit_predict.last_alpha = None


def fold_frames(con, scan: str, fold) -> tuple:
    """TRAIN rows up to the purge gap, plus the warmed-up PREDICT block.

    PREDICT starts `WARMUP_DAYS` trading days before validation_start -- the
    fold's own purge gap -- and stops at fold.validation_end capped at
    COHORT_LAST. Rows before validation_start are warm-up: never trained on,
    flagged `is_validation = False`.
    """
    select = ", ".join(f"CAST({c} AS FLOAT) AS {c}" for c in FEATURES)
    train = con.sql(f"""
        SELECT permno, date, tdi, {select}, CAST({TARGET} AS FLOAT) AS {TARGET}
        FROM {scan}
        WHERE aligned AND date <= DATE '{fold.train_end}' AND {TARGET} IS NOT NULL
    """).df()

    validation_end = min(pd.Timestamp(fold.validation_end), pd.Timestamp(COHORT_LAST))
    predict_frame = con.sql(f"""
        SELECT permno, date, tdi, {select}
        FROM {scan}
        WHERE aligned
          AND tdi >= (SELECT tdi FROM {scan} WHERE date = DATE '{fold.validation_start}'
                      LIMIT 1) - {WARMUP_DAYS}
          AND date <= DATE '{validation_end.date()}'
    """).df()
    predict_frame["is_validation"] = predict_frame.date >= pd.Timestamp(fold.validation_start)
    return train, predict_frame


def main() -> None:
    import duckdb

    if not PANEL.exists():
        sys.exit("Factor panel not found. Run src/features/build_factor_panel.py first.")
    PREDICTIONS.parent.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    scan = f"parquet_scan('{(PANEL / '**' / '*.parquet').as_posix()}')"
    dates = con.sql(f"SELECT DISTINCT date FROM {scan} WHERE aligned ORDER BY date").df().date
    splits = walk_forward_splits(dates, last_evaluable=COHORT_LAST)

    predictions, fold_models = [], []
    for _, fold in splits.iterrows():
        train, predict_frame = fold_frames(con, scan, fold)
        for name in MODELS:
            start = time.time()
            predicted = fit_predict(train, predict_frame, name)
            elapsed = time.time() - start

            out = predict_frame[["permno", "date", "tdi", "is_validation"]].copy()
            out["fold"], out["model"], out["prediction"] = fold.fold, name, predicted
            predictions.append(out)

            fold_models.append({
                "fold": fold.fold, "model": name,
                "train_rows": len(train), "predict_rows": len(predict_frame),
                "validation_rows": int(predict_frame.is_validation.sum()),
                "train_start": fold.train_start, "train_end": fold.train_end,
                "validation_start": fold.validation_start, "validation_end": fold.validation_end,
                "chosen_alpha": fit_predict.last_alpha if name == "ridge" else "",
                "fit_seconds": elapsed,
            })
            print(f"fold {fold.fold:2d} {name:5s}  train {len(train):>9,}"
                  f"  predict {len(predict_frame):>7,}  {elapsed:6.1f}s", flush=True)

    result = pd.concat(predictions, ignore_index=True)[
        ["permno", "date", "tdi", "fold", "model", "prediction", "is_validation"]]
    result["permno"] = result.permno.astype(int)
    result["tdi"] = result.tdi.astype(int)
    result["fold"] = result.fold.astype(int)
    result["model"] = result.model.astype(str)
    result["prediction"] = result.prediction.astype(float)
    result["is_validation"] = result.is_validation.astype(bool)

    assert result.date.max() <= pd.Timestamp(COHORT_LAST), "prediction past the sealed period"
    assert result.prediction.notna().all(), "NaN prediction"

    result.to_parquet(PREDICTIONS, index=False)
    pd.DataFrame(fold_models).to_csv(OUT / "fold_models.csv", index=False)
    print(f"\nWrote {PREDICTIONS} ({len(result):,} rows)")
    print(f"Wrote {OUT / 'fold_models.csv'}")


if __name__ == "__main__":
    main()
