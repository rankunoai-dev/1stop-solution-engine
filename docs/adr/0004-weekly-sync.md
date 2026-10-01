# ADR 0004 — Weekly sync with an admin-only manual trigger

**Status**: Accepted (owner decision, 2026-10-01) · **Decision log**: D-06 · **Risk**: R-08

## Context
v1 specified a weekly batch sync. The investigation proposed daily deltas because tools in development change often. The owner chose weekly.

## Decision
- One weekly job (Sunday 02:00 IST): check the Drive change token and each repo's last commit; re-ingest only changed files (content hash); then run compliance scoring.
- No webhooks and no daily ingestion jobs.
- An admin-only "sync now" (all sources or one) for development and testing.

## Consequences
Answers can lag a tool's latest changes by up to a week. Every answer shows each cited document's date, and docs older than a tool's last release are down-weighted. Unchanged repos cost nothing to check.
