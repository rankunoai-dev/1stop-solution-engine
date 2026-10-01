# RankUno 1Stop

One knowledge base about every RankUno in-house tool, built from all of each tool's documentation and searched with hybrid (keyword + semantic) RAG. Staff reach it in two places:

- **The 1Stop web app:** "Which tool already solves my problem?" Tool discovery, with honest per-requirement comparison.
- **An assistant embedded inside each in-house tool** (RAE, prompt-engine and the tools in development): "How do I use this tool?" Answers come from that tool's docs, with citations.

Internal first, minimum spend. Full framing: [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md).

---

## Status

| | |
| :-- | :-- |
| **SDLC step** | Gate G2 **approved 2026-10-01** ([ADR 0000](docs/adr/0000-architecture-approval.md)); Step 6 implementation of R0 in progress |
| **Phase** | Architecture and R0/R1 plan drafted (2026-10-01). Investigation compressed by owner decision: remaining spikes run as early build slices. |
| **Code** | None yet. No production code is written until the Step 3 HITL architecture approval (Gate G2). |
| **Approved architecture** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| **Approver** | AI Lead (all gates during testing) |
| **Last updated** | 2026-10-01 |

## What works today

| Capability | Since |
| :-- | :-- |
| Development environment and the full quality gate (format, lint, dependency layers, strict types, tests with an 85% coverage floor) | R0.1 |
| CI on GitHub Actions: the same gate plus a gitleaks secret scan of the full history | R0.1 (runs once the GitHub remote exists) |

Nothing user-facing runs yet. This section lists only what works (SDLC Step 8).

### Development setup (Windows)

Requires Python 3.11+.

```powershell
.\scriptsootstrap.ps1   # creates .venv, installs dev tools, installs pre-commit hooks
.\scriptserify.ps1      # Step 7 gate; must pass before any slice is reported complete
```

Configuration: copy `.env.example` to `.env`. Nothing reads it yet; it lists every variable the architecture defines.

---

## Documents

| Document | Read it for |
| :-- | :-- |
| [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) | The two problems, personas, goals, non-goals, constraints, success measures, assumptions to validate, glossary. |
| [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) | Findings F-01…F-23, an element-by-element review of v1, the candidate architecture, the in-tool assistant, and the minimum-cost design (§9.7). |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | **The Step 2 blueprint:** components, data model, contracts, ingestion, hybrid search SQL, answer pipeline, SSE protocol, spend caps, auth, API, deployment. §16 lists the six choices needed at Gate G2. |
| [docs/IMPLEMENTATION_PLAN_R0_R1.md](docs/IMPLEMENTATION_PLAN_R0_R1.md) | **The Step 4 plan:** 13 R0 slices and 15 R1 slices, file by file, with tests and exit criteria. |
| [docs/adr/](docs/adr/) | Decision records 0001–0008 and the Gate G2 approval record (0000). |
| [docs/investigation/INVESTIGATION_PLAN.md](docs/investigation/INVESTIGATION_PLAN.md) | Phases 0–11 with workstreams, spikes (≤ $15 total), deliverables and exit gates, then the delivery roadmap (R0–R5). |
| [docs/investigation/DECISION_LOG.md](docs/investigation/DECISION_LOG.md) | 29 design decisions (7 already decided by the owner), each with a recommendation and the evidence it needs. |
| [docs/investigation/RISK_REGISTER.md](docs/investigation/RISK_REGISTER.md) | 28 risks with likelihood, impact and mitigations. |
| [docs/investigation/OPEN_QUESTIONS.md](docs/investigation/OPEN_QUESTIONS.md) | Questions per stakeholder group with interview guides; §2 records the answers so far and what's still blocking. |
| [docs/archive/v1/](docs/archive/v1/) | The original v1 documents, `docker-compose.yml` and `.env.example`, kept for traceability. v1 was superseded because it described an unvalidated design as if built (see INVESTIGATION_REPORT §4). |

---

## Investigation at a glance

```
P0  Mobilise & desk review                         ✅ done
P1  Discovery with tool owners & users ┐
P2  Inventory, sources, doc readiness  ┘  →  Gate G1: scope, pilot tool, LLM cap
P3  Knowledge model & access
P4  Ingestion & content safety
P5  Retrieval, matching & evaluation
P6  Assistant behaviour
P7  Assistant inside in-house tools
P8  Compliance, sync & notifications
P9  Security, cost & data
P10 Platform & operations
P11 Synthesis & HITL review            →  Gate G2: Step 3 approval, then build R0
```

Estimated at 5–6 weeks, or about 3 weeks on the fast track described in the plan.

---

## Standards this project follows

- RankUno 8-step SDLC and the binding standards in `C:\Users\RankUno\Documents\project-standards\docs\standards\`.
- The governed core from `project-standards/src/core` (`StrictModel`, `BaseTool`, `GuardrailEngine`, `CostLedger`), to be copied verbatim when the build starts, following prompt-engine ADR 0001 (decision D-26).
- Existing RankUno infrastructure (Railway, Supabase free tier, Sentry, Cloudflare), with free and local components first (decisions D-18, D-28).

---

Internal proprietary software, RankUno Technologies. All rights reserved.
