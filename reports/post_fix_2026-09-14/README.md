# Post-fix research recomputation

Generated: 2026-09-15T04:53:06Z

These outputs were recomputed **after** the source corrections to factor ranks,
backtest turnover / holdings / terminal costs, missing-return handling, Spearman
IC, drift-aware trading, formation-versus-evaluation separation, t-1 eligibility
and the cleaner's marking scope (2026-09-14 review). They are a **correction
audit**, not a second sealed test.

| Location | Role |
|----------|------|
| `reports/` (sibling of this folder) | **Pre-fix** research record, including the original sealed 2024–2025 artifacts under `reports/week6/` |
| `reports/post_fix/` (this tree) | Corrected recomputation |
| `reports/post_fix/week6_audit/` | 2024–2025 locked-book **audit** (same specification; separate label; sealed files untouched) |

**Missing-return policy:** held names with NULL daily `ret` (delistings / gaps in
this CRSP export, which has no delisting-return field) accrue **0** that day and
are counted in `positions_without_return`. They are not dropped from the P&L sum
via SQL NULL-skipping, and they do not abort the run.

Do not treat `week6_audit` as replacing the sealed one-shot result. Compare it
to `reports/week6/` when auditing how the bug fixes change the held-out numbers.
