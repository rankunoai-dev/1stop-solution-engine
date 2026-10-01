# ADR 0000 — Gate G2: architecture approval (SDLC Step 3)

**Status**: **APPROVED** 2026-10-01 (owner, in the working session), with amendments G2-4 and G2-7
**Documents under review**: [ARCHITECTURE.md](../ARCHITECTURE.md) (RKN-1STOP-ARCH-V1), [IMPLEMENTATION_PLAN_R0_R1.md](../IMPLEMENTATION_PLAN_R0_R1.md), ADRs 0001–0007

## What approval means

Approving this record approves every **[Proposed]** item in the architecture, ADRs 0001–0007, and the R0/R1 plan. It authorises implementation to start at slice R0.1. **[Provisional]** items stay provisional until their spike reports are accepted.

## Answers required (ARCHITECTURE §16)

| # | Choice | Recommendation | Owner answer |
| :-- | :-- | :-- | :-- |
| G2-1 | Web app stack | React + Vite SPA served by FastAPI | Approved |
| G2-2 | Database location | New free Supabase project `rankuno-1stop` | Approved |
| G2-3 | Code repository | `git init` here + private `rankunoai-dev/onestop` | Approved (remote created by the owner; `gh` CLI not installed here) |
| G2-4 | LLM for development | Claude Haiku 4.5 (alternative: Gemini Flash, no-training tier) | **Amended:** free local model via Ollama for development on the owner's laptop; cheap paid no-training model (Claude Haiku 4.5 or Gemini Flash) only for real-doc quality checks and the deployed pilot; Gemini free tier only with fake data |
| G2-5 | Spend caps | $1/day, $10/month | Approved |
| G2-6 | Admin-only "sync now" | Keep | Approved |
| G2-7 | Chat history storage (added) | Postgres `conversations`/`messages`; no Redis | **Approved:** Postgres only, behind a `ConversationStore` interface; a Redis cache (Upstash free) only if a measured slowdown appears |

## Write-risk and spend capabilities in R0/R1

| Capability | Risk class | Guardrail |
| :-- | :-- | :-- |
| Answer generation (LLM) | FINANCIAL | Persisted day/month caps, kill switch |
| Card drafting / FAQ extraction (LLM) | FINANCIAL | Same caps; one call per tool per change |
| Card publishing | DRAFT → human approval | Author or admin approval required |
| Sending email (codes, alerts) | WRITE (external) | Idempotency table; rate limits |
| Ingestion writes to own DB | internal | Secret gate fail-closed |

No capability writes to GitHub, Drive or any host tool.

## Approval

```
APPROVED
Approver: AI Lead (owner)
Date: 2026-10-01
Notes: Approved in the working session after two questions (Redis for chat
       history; free models in development). Both answered and recorded as
       amendments G2-4 and G2-7 above.
```
