# Implementation Progress

## Completed

- Week 0 research design locked in `research_protocol.md`.
- Raw CRSP export is immutable, checksummed, and ignored by Git.
- Streaming CSV-to-Parquet cleaner built and verified.
- Cleaned panel covers 2005-01-03 through 2025-12-31 with zero
  classification-date violations and zero exact duplicate `PERMNO`/date rows.
- Security filter locked to point-in-time corporate, regular-way, active
  common equities; `SecurityActiveFlg` is not used.

- Point-in-time eligible universe and 20-trading-day forward total-return
  target built from the processed Parquet panel only.
- Eligibility requires price >= $5, 20 prior daily dollar-volume observations
  averaging >= $5m, and at least 252 prior valid returns.
- Research-panel checks: 21,104,236 rows; 8,399,139 eligible rows; 8,321,030
  eligible rows with complete targets; all behavioral tests pass.
- Delisting-return limitation documented: this export has no explicit
  delisting-return field, so incomplete post-exit target windows are censored.

## Next

- Week 2: implement and evaluate the six locked single-factor signals.
