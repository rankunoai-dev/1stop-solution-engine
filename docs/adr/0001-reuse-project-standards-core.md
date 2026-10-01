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

## As built (slice R0.2, 2026-10-01)

**Finding:** `project-standards` does not pass its own quality gate. Run with its own configuration, 4 files fail `ruff format`, about 85 lint findings remain, and mypy reports 5 errors (mostly in `integrations/semrush.py`, which is not copied, but the core also fails). A byte-for-byte copy therefore cannot pass 1Stop's gate. prompt-engine hit the same issue; its core differs from the standards by about 800 lines despite its ADR saying "unchanged".

**What was done instead:** copy verbatim, then apply the smallest conformance patch, listed here in full so it can be ported back:

| File | Change | Behaviour change? |
| :-- | :-- | :-- |
| `src/core/guardrails.py`, `logger.py`, `schemas.py` | `ruff format` only (string joins, one set literal exploded one item per line) | No |
| `src/core/rate_limiter.py` | One error message split across two f-strings (line length) | No (identical message) |
| `src/core/base_tool.py` | `isinstance(cls.metadata, …)` → `isinstance(getattr(cls, "metadata", None), …)` plus a comment; mypy flagged the failure branch as unreachable because of the `ClassVar` annotation | No (same check; existing test still covers it) |
| `tests/core/*`, `tests/conftest.py` | None | — |

Tooling choices that made the rest pass without touching the core: ruff 0.16.9 and mypy 2.3.1 pinned exactly; isort `known-first-party = ["src", "tests"]`; tests exempt from docstring/annotation rules (as in prompt-engine).

**Result:** 66 core tests pass; core coverage 95%; format, lint, layer, and strict type checks pass.

**Port-back:** these five changes, plus the two settings above, should be applied to `project-standards` so its gate is green; recorded as a recommendation for the standards owner (INVESTIGATION_REPORT F-16).
