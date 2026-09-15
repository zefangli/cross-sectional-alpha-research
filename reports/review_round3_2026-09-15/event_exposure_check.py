"""Read-only diagnostic of retained allocations after known delisting returns.

Run from the repository: python reports/review_round3_2026-09-15/event_exposure_check.py
Uses the already-observed 2024-2025 correction-audit inputs and unchanged lock.
Does not invoke sealed mode or write results.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import duckdb
from src.evaluation import week6_final as w6
from src.portfolio.backtest import capped_neutral_weights


def main():
    with duckdb.connect(config={"threads": 3, "memory_limit": "2GB"}) as con:
        con.execute("SET enable_progress_bar=false")
        scan = f"read_parquet('{(w6.PANEL / '**' / '*.parquet').as_posix()}')"
        exposures = f"read_parquet('{(w6.EXPOSURES / '**' / '*.parquet').as_posix()}')"
        spec = w6.load_spec()
        hold = spec["hold_days"]
        last = w6.cohort_cutoff(con, scan, "2025-12-31", hold)
        frame = w6.score_frame(con, scan, exposures, spec, "2024-01-02", last)
        frame["w"] = capped_neutral_weights(frame, spec["weighting"], cap=spec["cap"])
        con.register("cohort_review", frame[["permno", "tdi", "w"]])
        research = (w6.ROOT / "data/processed/research_panel/**/*.parquet").as_posix()
        result = con.sql(f"""
            WITH cal AS (
                SELECT DISTINCT date, tdi FROM {scan}
                WHERE date BETWEEN DATE '2024-01-02' AND DATE '2025-12-31'
            ), held AS (
                SELECT c.permno, cal.tdi, SUM(c.w) / {hold} AS weight
                FROM cohort_review c JOIN cal
                    ON cal.tdi BETWEEN c.tdi + 1 AND c.tdi + {hold}
                GROUP BY c.permno, cal.tdi
            ), events AS (
                SELECT p.permno, MIN(f.tdi) AS event_tdi,
                       MIN(f.tdi) FILTER (p.ret IS NOT NULL) AS known_event_tdi
                FROM read_parquet('{research}') p
                JOIN {scan} f USING (permno, date)
                WHERE p.delisting_flag = 'Y' GROUP BY p.permno
            )
            SELECT SUM(ABS(h.weight)) AS total_missing_weight_days,
                   SUM(ABS(h.weight)) FILTER (e.event_tdi < h.tdi) AS after_any_event_weight_days,
                   SUM(ABS(h.weight)) FILTER (e.known_event_tdi < h.tdi) AS after_known_event_weight_days
            FROM held h LEFT JOIN {scan} p USING (permno, tdi)
            LEFT JOIN events e USING (permno)
            WHERE p.ret IS NULL AND h.weight <> 0
        """).df().iloc[0]
        print(result.to_string())
        print("Fraction after known event:",
              result.after_known_event_weight_days / result.total_missing_weight_days)


if __name__ == "__main__":
    main()
