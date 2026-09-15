# Snapshot of the 2026-09-14 correction audit

Frozen copy of the first correction audit, superseded by `reports/post_fix/` after the
2026-09-15 follow-up review (delisting event rows restored, observed-window marking in
Week 2, gap-trade diagnostic). Bulky per-book daily series were pruned; the locked book's
daily series, the 2024-2025 audit daily series, all summaries, protocols, replay targets
and figures are kept. Regenerate the rest with `git checkout` of the matching source and
`python -m src.evaluation.run_post_fix_audit`.
