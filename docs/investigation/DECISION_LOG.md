# RankUno 1Stop — Decision Log

| | |
| :-- | :-- |
| **Document ID** | `RKN-1STOP-DEC-V1` |
| **Date** | 2026-09-30 (owner answers applied) |
| **Owner and approver** | AI Lead |

> **Gate G2 approved on 2026-10-01** ([ADR 0000](../adr/0000-architecture-approval.md)). Every PROPOSED position used by [ARCHITECTURE.md](../ARCHITECTURE.md) is now approved; items marked provisional there are still confirmed by their spikes. ADRs 0001–0008 record the main ones.

Every consequential design choice is recorded here while it is open. Once it is **DECIDED** with evidence, it becomes an ADR in `docs/adr/` (Phase 11) and this entry links to it.

**Status values:** `OPEN` (no recommendation yet) · `PROPOSED` (recommendation made, evidence pending) · `DECIDED` (settled by the owner or by evidence) · `SUPERSEDED`.

## Summary

| ID | Decision | Status | Current position | Decided in |
| :-- | :-- | :-- | :-- | :-- |
| D-01 | Order: internal first or SaaS first | **DECIDED** 2026-09-30 | Internal first | Owner |
| D-02 | Build vs buy | PROPOSED | Build (owner direction); 1-hour sanity scan of alternatives only | Gate G1 |
| D-03 | Platform shape | **DECIDED** 2026-09-30 | One engine, one internal knowledge base, two channels (web app + in-tool widget); `space_id` kept for later | Owner |
| D-04 | Source of truth for the tool registry | PROPOSED | Excel registry in Drive stays the master for now; 1Stop reads it and owns the richer card | P4 |
| D-05 | Where tool content comes from | PROPOSED | GitHub repos (docs) + Drive (registry, any zips) | P2 |
| D-06 | Sync cadence | **DECIDED** 2026-10-01 | Weekly scheduled sync; admin-only manual trigger; no webhooks | Owner |
| D-07 | Vector store | PROPOSED | pgvector on Supabase free tier | P5 |
| D-08 | Keyword search | PROPOSED | Postgres full-text search + trigram, RRF fusion in SQL | P5 |
| D-09 | Reranker | PROPOSED | None, unless the golden set proves a need | P5 |
| D-10 | Embedding model | PROPOSED | Free local open-source model on CPU; paid only if it fails S-06 | P5 |
| D-11 | LLM providers and routing | **DECIDED** at G2 (ADR 0008) | Free local Ollama model in development; Haiku 4.5 / Gemini Flash paid no-training tier for real-doc checks and the pilot | Owner |
| D-12 | Intent routing | PROPOSED | No separate router; rewrite/intent folded into the answer call where possible | P6 |
| D-13 | Tone enforcement | PROPOSED | Persona in the prompt + offline judge; safety exempt | P6 |
| D-14 | Matrix scoring | PROPOSED | Must-have gate, effort-scaled ADAPTABLE, UNKNOWN, evidence; one call for all candidates | P5 |
| D-15 | Frontend stack | **DECIDED** at G2 | React + Vite SPA served by FastAPI; widget a separate tiny bundle | Owner |
| D-16 | Widget architecture | PROPOSED | Script-tag loader + iframe; React wrapper for React tools | P7 |
| D-17 | Widget identity | PROPOSED | Staged: per-tool key + origin allowlist → tool-signed user token → Entra ID | P7 |
| D-18 | Hosting | PROPOSED | One Railway service + Supabase free + Cloudflare; no Upstash in release 1 | P10 |
| D-19 | Jobs and scheduling | PROPOSED | In-process scheduler + Postgres job table (no Celery/broker) | P10 |
| D-20 | Email channel | **DECIDED for testing** | Test Gmail SMTP now; Microsoft 365 (Graph) later, behind one interface | Owner |
| D-21 | Staff sign-in | **DECIDED (staged)** | Allowlisted email login while testing; Microsoft Entra ID before rollout | Owner |
| D-22 | LLM observability | PROPOSED | Postgres `llm_trace` table + Sentry free | P10 |
| D-23 | Conversation retention | PROPOSED | 180 days content, aggregates kept; confirm with owner | P9 |
| D-24 | Web-search fallback | PROPOSED | Off | P6 |
| D-25 | When the bot can't answer | PROPOSED | "Ask the maintainer" (pre-filled message) + gap list; answers become FAQs | P7 |
| D-26 | Reuse of project-standards core | PROPOSED | Copy `src/core` verbatim (prompt-engine ADR 0001) | P10 |
| D-27 | Access isolation | PROPOSED | App-level `space_id`/`restricted` checks now; Postgres RLS when a second space appears | P3 |
| D-28 | Cost posture | **DECIDED** 2026-09-30, extended 2026-10-01 | Minimum spend; costs kept low throughout initial development; caps proposed: $1/day and $10/month LLM (awaiting owner's numbers, Q-L07) | Owner |
| D-29 | Tool ownership model | **DECIDED** 2026-09-30 | Author needed only for the onboarding handover; maintainer (default: admin) afterwards | Owner |

---

## Details

### D-01 Order — DECIDED (internal first)
- **Decision (owner, 2026-09-30):** Internal first. The first releases serve RankUno staff: the catalog and the assistant inside in-house tools.
- **Consequence:** External customers, public abuse defences beyond basics, and end-user privacy law are out of release scope.

### D-02 Build vs buy
- **Position:** Build, per owner direction and the minimum-spend rule. Paid vendor products for either problem (Backstage hosting, Glean, Intercom Fin, Kapa.ai, Inkeep, etc.) conflict with minimum spend or with RankUno-specific needs (the comparison matrix, embedding into tools under development).
- **Remaining work:** A one-hour check that no free, self-hostable option (e.g. Backstage's software catalog) would remove a large part of the build. Record the result in `research/BUILD_VS_BUY.md`.

### D-03 Platform shape — DECIDED
- **Decision (2026-09-30):** One engine and one knowledge base about all in-house tools, used by two channels: the 1Stop web app ("which tool?") and the widget inside each tool ("how do I use this tool?").
- **Future-proofing:** `space_id` on content and conversations, so an external space can be added later without restructuring.

### D-04 Source of truth for the tool registry
- **Position:** The Excel registry in Google Drive remains the master list of tools and owners (owner decision). 1Stop reads it daily and validates it (missing fields become compliance items). The richer **tool card** (problem, inputs/outputs, how to run, capabilities) lives in 1Stop, because Excel cells can't hold it well.
- **Identity:** 1Stop assigns its own UUID per tool and stores the registry row key and Drive file ID as references (F-08), so renaming or moving the file doesn't create duplicates.
- **Evidence needed:** S-02 (is it `.xlsx` or converted to a Google Sheet? which columns? how complete?).

### D-05 Where tool content comes from
- **Position:** GitHub repositories for documentation (README, `docs/`, ADRs, `CLAUDE.md`, OpenAPI); Drive for the registry and any zips of tools not in Git.
- **GitHub access, cheapest option:** a fine-grained read-only token on selected repos. No GitHub App or webhooks (weekly sync, D-06).

### D-06 Sync cadence
- **Decision (owner, 2026-10-01):** Weekly sync only, as in v1.
- **How:** one weekly job checks the Drive change token and each repo's last commit, re-ingests only what changed, then runs compliance scoring. No webhooks, no daily jobs.
- **Development aid:** an admin-only `sync now` command/button, so the AI Lead can re-ingest a tool immediately while building and testing. Not exposed to other users.
- **Consequence:** answers can be up to a week behind a tool's latest changes. Mitigated by showing each cited doc's date in the answer (R-08).

### D-07 Vector store
- **Position:** pgvector on the existing Supabase project (free tier). No Qdrant (extra service, extra cost).
- **Switch if:** S-05 misses recall/latency targets that tuning can't fix.

### D-08 Keyword search
- **Position:** Postgres full-text search (weighted title/headings/body) + `pg_trgm` for partial tool names and identifiers, fused with vector results by Reciprocal Rank Fusion in one SQL query. This is the "hybrid" part of hybrid RAG.

### D-09 Reranker
- **Position:** None in release 1. Add only if S-05 shows a gain of ≥ 0.03 recall@5 or MRR, and prefer a free local cross-encoder over a paid API.

### D-10 Embedding model
- **Position:** Start with a small open-source embedding model running on CPU in the worker (e.g. a BGE- or E5-class model through `fastembed`): zero API cost, and nothing leaves RankUno's infrastructure. S-06 compares it with one cheap hosted model; switch only if the free one misses the target.
- **Note:** Store `embedding_model` and dimension per chunk, so a later switch is a re-embed job, not a redesign.

### D-11 LLM providers and routing
- **Position:** The cheapest model that passes groundedness and helpfulness on the golden set (Haiku-/Flash-class candidates, e.g. Claude Haiku 4.5, Gemini Flash; others as they appear), behind the provider abstraction.
- **Hard rule:** internal docs are only sent to tiers whose terms say inputs are **not** used for training (R-24). A free tier that trains on inputs may be used only with synthetic test data.
- **Escalation:** a stronger model only for offline, rare tasks (card drafting, matrix) if the cheap one fails S-04/S-07.

### D-12 Intent routing
- **Position:** No separate router (v1's 3 tiers dropped). First-turn questions go straight to retrieval + answer. Follow-ups use the recent conversation turns inside the same answer call; a separate rewrite call is added only if follow-up accuracy is below 95% in P6.2. The saving is one LLM call per question.

### D-13 Tone enforcement
- **Position:** Persona in the system prompt, explicit safety exemption, offline judge in CI (S-08). No regex rewriting of streamed text (F-09).

### D-14 Matrix scoring
- **Position:** As in INVESTIGATION_REPORT §8.3. For cost, all top candidates (≤ 5) are evaluated in **one** structured call, and only when the user asks to compare or the question lists several requirements.

### D-15 Frontend stack
- **Options:** Next.js 16 (RAE) · React + Vite + Ant Design (prompt-engine).
- **Position:** Use whichever the AI Lead maintains more easily. The widget is a separate small bundle (vanilla TypeScript or Preact) in either case.

### D-16 Widget architecture
- **Position:** Script-tag loader + iframe (works in every tool whatever its framework), with a thin React wrapper for React/Next.js tools. Served from the API service or Cloudflare at no extra cost.

### D-17 Widget identity
- **Position (staged):**
  1. Testing: per-tool publishable key + allowed origins (the tool's URL); rate limit + daily cap.
  2. Pilot: the host tool's backend signs a short-lived token with the user's email (tools like prompt-engine already have logins).
  3. Rollout: Microsoft Entra ID, shared by the widget and the web app.
- **Design now for later:** users are keyed by email from day one, so Entra ID slots in without migrating data.

### D-18 Hosting
- **Position:** One Railway service running the API and background jobs; Supabase free tier for Postgres/pgvector; Cloudflare for DNS/TLS. **No Upstash in release 1**: rate-limit counters and job state live in Postgres. Docker Compose for local development only.

### D-19 Jobs and scheduling
- **Position:** An in-process scheduler inside the Railway service, plus a Postgres `jobs` table (`SELECT … FOR UPDATE SKIP LOCKED`) for retries. No Celery, no broker, no idle polling cost. Revisit if jobs need their own service.
- **Evidence needed:** S-12 (reduced: verify restart safety and retries).

### D-20 Email channel — DECIDED for testing
- **Decision:** During testing, send from the test Gmail via SMTP with an app password. Later, send from a Microsoft 365 mailbox via Graph `sendMail`. One `EmailSender` interface, two adapters.
- **Reuse:** newsletter-rankuno's idempotent delivery records and pre-send checks.

### D-21 Staff sign-in — DECIDED (staged)
- **What SSO means here:** "Single sign-on" lets staff open 1Stop with their existing company Microsoft account (Entra ID) instead of creating another password. Leavers lose access automatically when their company account is disabled, and MFA comes from Microsoft.
- **Decision:** Testing: an allowlist of staff emails with one-time email codes, or a single test login. Before rollout beyond the pilot group: "Sign in with Microsoft" (Entra ID, OIDC). Roles (staff/owner/admin) are stored in 1Stop.

### D-22 LLM observability
- **Position:** A Postgres `llm_trace` table per turn (prompt version, chunk IDs, model, tokens, cost, latency, feedback) + Sentry free tier. No paid or extra-service tracing in release 1.

### D-23 Conversation retention
- **Position:** Keep message content 180 days, then delete; keep anonymised aggregates (counts, feedback, gap clusters) indefinitely. The owner confirms the values.

### D-24 Web-search fallback
- **Position:** Off. Answers come only from RankUno tool knowledge.

### D-25 When the bot can't answer
- **Position:** Say so, suggest a related tool if one fits, and offer "Ask the maintainer", which opens a pre-filled email or Teams message to the tool's current maintainer (D-29). The question is added to the maintainer's gap list. Once answered, the answer is added to the knowledge base as an FAQ, so the same question isn't escalated twice.

### D-26 Reuse of project-standards core
- **Position:** Copy `src/core/*` and `tests/core/*` verbatim (prompt-engine ADR 0001 pattern); do not copy `integrations/semrush.py`. Port prompt-engine's persisted daily cap and URL safety additions.

### D-27 Access isolation
- **Position (relaxed 2026-09-30):** One internal space, so access is enforced in application code (`space_id` and the `restricted` flag checked in every retrieval query, with tests). Postgres RLS is switched on in the same change that introduces a second space.

### D-28 Cost posture — DECIDED
- **Decision (owner, 2026-09-30):** Minimise dollar spend.
- **Rules:**
  1. Every component starts at its free or cheapest option (INVESTIGATION_REPORT §9.7).
  2. A paid upgrade requires a measured failure of a quality target on the golden set, recorded in this log.
  3. LLM spend caps are persisted in Postgres and enforced by `CostLedger`. **Development-phase proposal:** $1/day **and** $10/month hard ceilings, covering all LLM use (answers, card drafting, eval runs). When a cap is reached, LLM calls stop and the UI says so; search results without generated answers still work. Exact numbers await the owner (Q-L07).
  3a. **Owner direction (2026-10-01):** costs must stay low throughout initial development. So: the cheapest passing model by default; eval runs use small golden-set subsets except before a gate; card drafting runs once per tool; and no paid component is added during development without a recorded reason.
  4. Spike budget for the whole investigation: ≤ $15 (was ~$120).
  5. Don't save on secret scanning, tests, evaluation or backups; they cost time, not money.

### D-29 Tool ownership model — DECIDED
- **Decision (owner, 2026-09-30):** Once a tool is onboarded, its original owner is not needed.
- **Model:** two roles per tool.
  - **Author:** the person who built it. Needed once, for the **onboarding handover** (card review + handover questionnaire, INVESTIGATION_PLAN P4.8). Optional after that.
  - **Maintainer:** receives unanswered questions, thumbs-down answers and doc reminders, and approves card changes. Defaults to the **platform admin (AI Lead)** after handover. For a tool still in active development, the developer currently changing it stays the maintainer until the tool is marked stable (Q-A06).
- **Consequences:**
  1. Onboarding must capture the author's tacit knowledge (common questions, gotchas, error fixes, which docs are current) as FAQ documents, because afterwards nobody may be able to answer.
  2. Leavers need no special process: the registry keeps the author for history; routing uses the maintainer field.
  3. Digests for stable tools all go to the admin, concentrating load on one person (R-20, R-28). The gap loop (answer once, then it becomes an FAQ) keeps that load small.
