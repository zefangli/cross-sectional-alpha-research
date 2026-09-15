"""Bounded, repeatable review; preserves the original lock and sealed artifacts."""
from pathlib import Path
import hashlib
import json
import sys

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.evaluation import week6_final as w6
from src.portfolio.backtest import capped_neutral_weights

OUT = Path(__file__).resolve().parent


def main():
    protected = [p for p in (ROOT / 'reports/week6').rglob('*') if p.is_file()]
    protected.append(w6.SPEC_PATH)
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    with duckdb.connect(config={'threads': 3, 'memory_limit': '3GB'}) as con:
        con.execute('SET enable_progress_bar=false')
        scan = f"read_parquet('{(w6.PANEL / '**/*.parquet').as_posix()}')"
        exp = f"read_parquet('{(w6.EXPOSURES / '**/*.parquet').as_posix()}')"
        spec = w6.load_spec()
        targets = json.loads((ROOT / 'reports/post_fix/week5/replay_targets.json').read_text())
        if '--events-only' not in sys.argv and '--audit-only' not in sys.argv:
            print(w6.replay(con, scan, exp, spec, targets, OUT).to_string(index=False), flush=True)
        first, end, hold = '2024-01-02', '2025-12-31', spec['hold_days']
        last = w6.cohort_cutoff(con, scan, end, hold)
        if '--events-only' not in sys.argv:
            con.execute(f"CREATE VIEW audit_panel AS SELECT * FROM {scan} WHERE date BETWEEN DATE '{first}' AND DATE '{end}'")
            con.execute(f"CREATE VIEW audit_exposures AS SELECT * FROM {exp} WHERE date BETWEEN DATE '{first}' AND DATE '{end}'")
            daily, summary, _ = w6.run_locked_book(con, 'audit_panel', 'audit_exposures', spec, first, last, end)
            saved = pd.read_csv(ROOT / 'reports/post_fix/week6_audit/audit_daily.csv')
            for col in daily.select_dtypes(include='number'):
                assert np.allclose(daily[col], saved[col], rtol=1e-8, atol=1e-10, equal_nan=True), col
            print('Every numeric daily audit column reproduces.', flush=True)
            pd.Series(summary).to_csv(OUT / 'audit_summary_recomputed.csv')
        frame = w6.score_frame(con, scan, exp, spec, first, last)
        frame['w'] = capped_neutral_weights(frame, spec['weighting'], cap=spec['cap'])
        con.register('review_cohort', frame[['permno', 'tdi', 'w']])
        events = con.sql(f"""
            SELECT p.permno, p.date, p.tdi, p.ret, SUM(c.w)/{hold} AS event_weight
            FROM {scan} p JOIN review_cohort c ON p.permno=c.permno
                AND p.tdi BETWEEN c.tdi+1 AND c.tdi+{hold}
            WHERE p.delisting_flag='Y'
            GROUP BY p.permno, p.date, p.tdi, p.ret HAVING ABS(SUM(c.w))>1e-12
            ORDER BY p.date, p.permno
        """).df()
        events.to_csv(OUT / 'held_events.csv', index=False)
        unknown = events[events.ret.isna()]
        print('Held events:', len(events), 'Unknown payoff events:', len(unknown), flush=True)
        print(unknown.to_string(index=False), flush=True)
        print('Absolute NAV of unknown event claims:', unknown.event_weight.abs().sum(), flush=True)
        print('Signed NAV of unknown event claims:', unknown.event_weight.sum(), flush=True)
        clean = f"read_parquet('{(ROOT / 'data/processed/crsp_daily_panel/**/*.parquet').as_posix()}')"
        print(con.sql(f"SELECT COUNT(*) events, COUNT(*) FILTER (ret IS NULL) unknown_events FROM {clean} WHERE delisting_flag='Y'").df().to_string(index=False), flush=True)
    after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    assert before == after
    (OUT / 'protected_sha256.json').write_text(json.dumps(after, indent=2)+'\n')
    print('Original sealed directory and lock unchanged by this verification.', flush=True)


if __name__ == '__main__':
    main()
