"""Regressions for the 2026-09-14 review items that live in Week 4/5 code.

Items 1, 2 and 5 (engine drift, Week 2 formation, tie handling) are covered
next to the code they test in `test_week3.py`, `test_factor_eval.py` and
`test_research_panel.py`.
"""
import warnings

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.evaluation.week4_models import prediction_quality
from src.evaluation.week5_lock import lock_target


def _week4_inputs(predictions, targets, dates=("2020-01-02",)):
    dates = pd.to_datetime(list(dates))
    n = len(predictions)
    panel = pd.DataFrame({
        "permno": list(range(1, n + 1)) * (1 + len(dates)),
        "date": [pd.Timestamp("2019-01-01")] * n + [d for d in dates for _ in range(n)],
        "tdi": [0] * n + [i + 1 for i in range(len(dates)) for _ in range(n)],
        "aligned": True,
        "forward_return_20d": [0.0] * n + list(targets) * len(dates),
    })
    preds = pd.DataFrame({
        "permno": list(range(1, n + 1)) * len(dates),
        "date": [d for d in dates for _ in range(n)],
        "tdi": [i + 1 for i in range(len(dates)) for _ in range(n)],
        "fold": 1, "model": "gbm", "prediction": list(predictions) * len(dates),
        "is_validation": True,
    })
    folds = pd.DataFrame({"fold": [1], "train_end": [pd.Timestamp("2019-12-01")]})
    return panel, preds, folds


def _spearman(panel, preds, folds):
    con = duckdb.connect()
    con.register("fp", panel)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # one date: no HAC t
        _, metrics = prediction_quality(con, "fp", preds, folds)
    return float(metrics.mean_ic_spearman.iloc[0])


def test_week4_spearman_ignores_missing_targets():
    """Item 4: [1,2,3,0] vs [1,2,3,NULL] is +1.00 on complete pairs, not -0.20."""
    assert abs(_spearman(*_week4_inputs([1., 2., 3., 0.], [1., 2., 3., np.nan])) - 1.0) < 1e-12


def test_week4_spearman_uses_average_ranks_on_ties():
    """Item 5: tied predictions get average ranks, matching scipy."""
    ic = _spearman(*_week4_inputs([0., 0., 1., 2.], [1., 2., 3., 4.]))
    assert abs(ic - spearmanr([0., 0., 1., 2.], [1., 2., 3., 4.]).correlation) < 1e-12
    assert abs(ic - 0.9486832980505139) < 1e-12


def test_week4_hac_statistics_are_invariant_to_input_row_order():
    """Item 5: the daily IC series must be sorted by date before Newey-West."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2020-01-02", periods=40)
    n = 30
    panel = pd.DataFrame({
        "permno": np.tile(np.arange(1, n + 1), len(dates)),
        "date": np.repeat(dates, n), "tdi": np.repeat(np.arange(1, len(dates) + 1), n),
        "aligned": True, "forward_return_20d": rng.normal(size=n * len(dates)),
    })
    preds = panel[["permno", "date", "tdi"]].assign(
        fold=1, model="gbm", is_validation=True,
        prediction=0.3 * panel.forward_return_20d + rng.normal(size=len(panel)))
    folds = pd.DataFrame({"fold": [1], "train_end": [pd.Timestamp("2019-12-01")]})

    def run(panel, preds):
        con = duckdb.connect()
        con.register("fp", panel)
        _, m = prediction_quality(con, "fp", preds, folds)
        return m[["mean_ic_spearman", "ic_spearman_nw_tstat", "ic_pearson_nw_tstat"]].iloc[0]

    ordered = run(panel, preds)
    shuffled = run(panel.sample(frac=1, random_state=1), preds.sample(frac=1, random_state=2))
    assert np.allclose(ordered.values, shuffled.values, atol=1e-12)


def test_existing_lock_is_not_overwritten_by_a_rerun(tmp_path):
    """Item 7: the historical lock is immutable unless --relock is passed."""
    assert lock_target(tmp_path, relock=False).name == "locked_specification.json"
    (tmp_path / "locked_specification.json").write_text("{}")
    assert lock_target(tmp_path, relock=False).name == "reselection.json"
    assert lock_target(tmp_path, relock=True).name == "locked_specification.json"
