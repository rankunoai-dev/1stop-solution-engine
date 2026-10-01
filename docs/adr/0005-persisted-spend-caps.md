# ADR 0005 — Persisted daily and monthly LLM spend caps

**Status**: Principle Accepted (owner, 2026-09-30 / 2026-10-01); cap values Accepted at Gate G2 ($1/day, $10/month) · **Decision log**: D-28

## Context
The owner requires minimum spend, with costs kept low throughout initial development. prompt-engine ADR 0018 showed that an in-memory ceiling re-arms on every restart.

## Decision
- Every LLM call is a `BaseTool` with `RiskClass.FINANCIAL`.
- Before a call: reserve the estimated worst-case cost (counted input tokens + `max_output_tokens`, priced from a dated price table) against today's and this month's totals summed from `llm_calls`, under an advisory lock. Refuse if either cap would be exceeded.
- After a call: record the actual usage and cost.
- Unknown model price → refuse (fail closed). Kill switch `llm_enabled`. Alerts at 50/80/100%.
- When capped, search results still show; only generated answers stop.

## Consequences
Spend can't exceed the caps even across restarts or concurrent requests. Development work (eval runs, card drafting) shares the same caps, so they must be sized to the plan in IMPLEMENTATION_PLAN §2–3.
