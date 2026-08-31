"""Fixed chronological walk-forward splits.

Expanding training window, one calendar year of validation per fold, with a
purge between them. The purge is the point: an observation at date *t* carries a
target that runs to *t*+20 trading days, so training on dates up to the day
before validation would train on returns realised inside the validation year.
Training therefore stops 21 trading days before the validation year begins,
which leaves the last training target ending on the final trading day before
validation starts.

The splits are fixed here, once, and written out as an artefact. They are not
re-derived per experiment and they never extend past the sealed period.
"""
import pandas as pd

FIRST_VALIDATION_YEAR = 2014
LAST_VALIDATION_YEAR = 2023
HORIZON = 20


def walk_forward_splits(trading_dates, first_validation_year=FIRST_VALIDATION_YEAR,
                        last_validation_year=LAST_VALIDATION_YEAR,
                        horizon=HORIZON, last_evaluable=None) -> pd.DataFrame:
    """One expanding-window fold per validation year.

    `last_evaluable` caps every validation window, so the final fold cannot
    reach a target into the sealed period.
    """
    dates = pd.Series(pd.to_datetime(sorted(set(trading_dates)))).reset_index(drop=True)
    if last_evaluable is not None:
        dates = dates[dates <= pd.Timestamp(last_evaluable)].reset_index(drop=True)
    folds = []
    for year in range(first_validation_year, last_validation_year + 1):
        in_year = dates[dates.dt.year == year]
        if in_year.empty:
            continue
        start = int(in_year.index[0])
        train_end = start - horizon - 1
        if train_end < horizon:
            continue
        folds.append({
            "fold": len(folds) + 1,
            "train_start": dates.iloc[0].date(),
            "train_end": dates.iloc[train_end].date(),
            "train_days": train_end + 1,
            "purged_days": horizon,
            "validation_start": in_year.iloc[0].date(),
            "validation_end": in_year.iloc[-1].date(),
            "validation_days": len(in_year),
        })
    return pd.DataFrame(folds)
