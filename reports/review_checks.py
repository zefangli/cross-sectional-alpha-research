"""Synthetic reproductions from the 2026-09-14 review, now asserting the
corrected behaviour.

Run: python reports/review_checks.py
Each block was written by the reviewer to demonstrate a defect; the assertions
were flipped once the production code was fixed, as the original docstring
asked. The same cases are pinned as pytest regressions in
tests/test_week3.py, tests/test_factor_eval.py and tests/test_review_2026_09_14.py.
No research data or report artifacts are read or written.
"""
from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb
import numpy as np
import pandas as pd

from src.evaluation.factor_eval import cross_section_query
from src.evaluation.week4_models import prediction_quality
from src.portfolio.backtest import daily_book


def main():
    with duckdb.connect() as con:
        dates = pd.bdate_range("2020-01-01", periods=5)
        panel = pd.DataFrame([
            dict(permno=p, date=d, tdi=t,
                 ret=0.1 if p == 1 and t == 1 else 0.0,
                 value_weighted_market_return=0.0, delisting_flag="N")
            for p in (1, 2) for t, d in enumerate(dates)
        ])
        cohort = pd.DataFrame({"permno": [1, 2], "tdi": [0, 0], "w": [.5, -.5]})
        con.register("panel", panel)
        con.register("cohort", cohort)
        book = daily_book(con, "panel", "2020-01-01", "2020-02-01", hold=2)
        weights, returns = np.array([.25, -.25]), np.array([.1, 0.])
        drifted = weights * (1 + returns) / (1 + weights @ returns)
        required_trade = np.abs(weights - drifted).sum()
        reported_trade = book.set_index("tdi").loc[2, "traded"]
        assert abs(reported_trade - required_trade) < 1e-12
        print(f"Drift: reported trade={reported_trade:.6f} equals the trade to restore "
              f"target weights={required_trade:.6f} of NAV (before costs)")

        xs = pd.DataFrame({
            "permno": range(1, 11), "date": pd.Timestamp("2020-01-01"),
            "tdi": 1, "f": range(1, 11), "forward_return_20d": [.01] * 10,
        })
        con.register("elig", xs)
        before = con.sql(cross_section_query("elig")).df()
        xs.loc[xs.permno == 10, "forward_return_20d"] = np.nan
        con.unregister("elig")
        con.register("elig", xs)
        after = con.sql(cross_section_query("elig")).df()
        assert 10 in before.permno.values and 10 in after.permno.values
        assert after.set_index("permno").loc[10, "decile"] == 10
        print("Future availability: the highest-signal stock stays in the Week 2 formation "
              "universe when only its future target becomes missing")

        panel = pd.DataFrame({
            "permno": [1, 2, 3, 4] * 2,
            "date": pd.to_datetime(["2019-01-01"] * 4 + ["2020-01-02"] * 4),
            "tdi": [0] * 4 + [1] * 4, "aligned": True,
            "forward_return_20d": [0., 0., 0., 0., 1., 2., 3., np.nan],
        })
        predictions = pd.DataFrame({
            "permno": [1, 2, 3, 4], "date": pd.Timestamp("2020-01-02"),
            "tdi": 1, "fold": 1, "model": "gbm",
            "prediction": [1., 2., 3., 0.], "is_validation": True,
        })
        folds = pd.DataFrame({"fold": [1], "train_end": [pd.Timestamp("2019-12-01")]})
        con.register("fp", panel)
        # A single date cannot support a HAC t-stat; only IC is inspected here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            _, metrics = prediction_quality(con, "fp", predictions, folds)
            reported_ic = metrics.mean_ic_spearman.iloc[0]
            assert np.isclose(reported_ic, 1.0)
            print(f"Missing target: Week 4 Spearman={reported_ic:.2f} (complete pairs only)")

            panel.loc[panel.tdi == 1, "forward_return_20d"] = [1., 2., 3., 4.]
            predictions["prediction"] = [0., 0., 1., 2.]
            con.unregister("fp")
            con.register("fp", panel)
            _, metrics = prediction_quality(con, "fp", predictions, folds)
            reported_ic = metrics.mean_ic_spearman.iloc[0]
            expected_ic = predictions.prediction.corr(pd.Series([1., 2., 3., 4.]), method="spearman")
            assert np.isclose(reported_ic, expected_ic)
            print(f"Ties: Week 4 Spearman={reported_ic:.9f} equals "
                  f"average-rank Spearman={expected_ic:.9f}")
    print("ALL REVIEW CHECKS PASS UNDER THE CORRECTED CODE")


if __name__ == "__main__":
    main()
