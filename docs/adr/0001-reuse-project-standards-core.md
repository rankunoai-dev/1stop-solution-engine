# ADR 0001 — Reuse the project-standards core by copying it

**Status**: Accepted (Gate G2, 2026-10-01) · **Decision log**: D-26

## Context
RankUno's standards require the governed core (`StrictModel`, `BaseTool`, `GuardrailEngine`, `CostLedger`, logger, errors, retry). It exists, tested, in `project-standards/src/core`, but it is not published as a package. prompt-engine faced the same situation (its ADR 0001).

## Decision
Copy `src/core/*` and `tests/core/*` verbatim. Do not copy `integrations/semrush.py`, which violates the standards. 1Stop-specific additions live outside `core` (`modules/platform/spend.py` for the persisted ledger, `modules/platform/settings.py`).

## Alternatives considered
- Depend on project-standards as a package: not published or versioned.
- Rewrite the core: invites drift from the class names the standards reference.

## Consequences
Two copies exist; fixes are ported back deliberately. The core's in-memory `CostLedger` is wrapped by a persisted guard so restarts can't re-arm budgets (ADR 0005).
