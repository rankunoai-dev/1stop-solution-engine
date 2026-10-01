# RankUno 1Stop — Problem Statement

| | |
| :-- | :-- |
| **Document ID** | `RKN-1STOP-PS-V2` |
| **Version** | 2.1 (draft) |
| **Status** | Under investigation (SDLC Step 1). Scope decisions of 2026-09-30 applied (see §0). |
| **Date** | 2026-09-30 |
| **Owner and approver** | AI Lead (approves all gates during the testing period) |
| **Supersedes** | v2.0 (2026-09-29); v1.0 archived at [docs/archive/v1/PROBLEM_STATEMENT.md](docs/archive/v1/PROBLEM_STATEMENT.md) |

> Every statement is tagged with how well we know it:
> **[Decided]** settled by the owner;
> **[Observed]** we have seen evidence, cited inline;
> **[Reported]** someone told us, not yet verified;
> **[Assumed]** we believe it but have no evidence yet. Each assumption has an ID (A-nn) and is validated in the [investigation plan](docs/investigation/INVESTIGATION_PLAN.md).

---

## 0. Scope decisions (2026-09-30)

| # | Decision | Effect |
| :-- | :-- | :-- |
| 1 | **Internal first.** | The first release serves RankUno staff only. External customers are out of scope until a later decision. |
| 2 | **The embedded assistant goes into RankUno's in-house tools** (several are in development), not into external SaaS products. | A staff member using a tool can ask the assistant about that tool. Both audiences are staff. |
| 3 | **All documentation about each tool is ingested** and searched with a hybrid (keyword + semantic) RAG approach. | One knowledge base about every tool, used by the 1Stop app and by every embedded assistant. |
| 4 | **Excel registry stays in Google Drive.** | The Drive connector is needed from the first release. |
| 5 | **Testing runs on a Gmail account;** Microsoft Entra ID will be the staff identity later. | Simple login while testing; Microsoft sign-in added before wider rollout. |
| 6 | **The AI Lead approves everything during testing.** | One approver for all gates. |
| 7 | **Minimum dollar spend.** | Free tiers, local or free models where quality allows, and the fewest LLM calls per question. Every design choice records its cost. |
| 8 | **Weekly sync** (2026-10-01). | Docs are re-read once a week; an admin-only manual trigger exists for development. Answers show their source date. |
| 9 | **Costs stay low throughout initial development** (2026-10-01). | Hard LLM ceilings per day and per month during development; proposed $1/day and $10/month, numbers to be confirmed. |

---

## 1. Summary

RankUno builds many in-house tools: crawlers, report builders, prompt trackers, newsletters, location-intelligence engines, and more in development. Two things go wrong with them:

**Problem A: people can't find the tools.** Tools live wherever their authors put them and are documented unevenly. A colleague with the same problem cannot find the existing tool, so they rebuild it.

**Problem B: people can't get help inside a tool.** Someone using a tool gets stuck: which config to pick, what an error means, how to import a file. The answer is in the tool's docs, ADRs or its author's head, but not where the user is working.

**Both problems need one thing:** a single, governed **knowledge base about every in-house tool**, built from all of each tool's documentation, that answers questions with grounded, cited answers **where people already are**.

```
                ┌───────────────────────────────────────────────┐
                │           1Stop knowledge engine              │
                │  ingest docs → secure → index (hybrid RAG)    │
                │  retrieve → grounded answer with citations    │
                └───────────────────────┬───────────────────────┘
                                        │
                     One knowledge base about all in-house tools
                     (catalog cards + every doc, ADR, README, guide)
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             │                                                     │
   ┌─────────▼──────────┐                           ┌──────────────▼─────────────┐
   │   1Stop web app    │                           │  Assistant embedded in     │
   │  "Which tool       │                           │  each in-house tool        │
   │   solves my        │                           │  (RAE, prompt-engine, …)   │
   │   problem?"        │                           │  "How do I use this tool?" │
   └────────────────────┘                           └────────────────────────────┘
```

The design keeps a **knowledge space** concept, so that external products or clients could be added later without a rebuild (Q-L06). In release 1 there is only one space: RankUno internal.

---

## 2. Who has the problem

| Persona | What they need | Today |
| :-- | :-- | :-- |
| **Tool seeker** (engineer, analyst, PM) | "Has anyone already solved X?" answered in under a minute, with honest fit information. | Asks around, searches Drive by filename, or rebuilds. [Assumed A-01] |
| **Tool user** (staff using an in-house tool) | "How do I do X in this tool?" answered inside the tool, in context. | Messages the author or reads through repo files. [Assumed A-03] |
| **Tool owner** (author) | Their work found and used, fewer repeated questions, little documentation burden. | Answers the same questions repeatedly; no nudge to document. [Assumed A-02, A-05] |
| **Catalog admin** | A complete, current catalog without chasing people. | Excel registry in Drive, maintained by hand. [Decided: registry stays in Drive] |
| **Tool developer** (adds the assistant to a tool) | A few lines of code to embed it, without breaking the tool's UI. | Each tool builds its own chat. [Observed: `RAE/rankuno-toolkit` has its own "AI chat"] |
| **Platform operator** (AI Lead) | One engine to secure, monitor and pay for, at minimum cost. | Nothing shared yet. [Observed] |

---

## 3. Current state and pain points

| # | Pain point | Evidence |
| :-- | :-- | :-- |
| 3.1 | Tools are scattered across the GitHub org `rankunoai-dev`, local folders and Google Drive. | **[Observed]** `rankunoai-dev/rae-engine`, `custom-tool` (accounts record RKN-REC-2026-V1); Desktop folders `RAE`, `prompt-engine`, `newsletter-rankuno`, `rankuno-loc-intel`, `rankuno-engine1`; Excel registry in Drive [Decided]. |
| 3.2 | Copies and forks multiply with no canonical version. | **[Observed]** `rankuno-engine1/` contains copies of `project-standards/` and `RAE/`. |
| 3.3 | Keyword search fails when the seeker's words differ from the author's. | [Assumed A-06] |
| 3.4 | Documentation quality and shape vary widely. | **[Observed]** prompt-engine has 25 ADRs and briefs in `docs/`; rankuno-loc-intel has 30+ loose phase/status markdown files at its root; RAE keeps context in `CLAUDE.md` files. |
| 3.5 | Tool artifacts can contain secrets. | **[Observed]** RAE README: old backend history "contains a committed `.env`". |
| 3.6 | Nobody knows which tools are alive, deprecated or duplicated. | [Assumed A-07] |
| 3.7 | Tools under active development change weekly, so any static documentation goes stale fast. | **[Reported]** several tools in development (2026-09-30). |
| 3.8 | Each tool that wants an AI helper builds its own. | **[Observed]** RAE "AI chat". |

**Root cause:** knowledge about each tool exists, but it is not captured in one structured, searchable form, not reachable where the question arises, and nothing tells anyone what is missing.

---

## 4. Goals

| ID | Goal |
| :-- | :-- |
| **G1** | **Findability.** A seeker describes a problem in plain language and sees the relevant tools, with honest per-requirement fit and cited evidence. |
| **G2** | **Reuse.** Easy path from "found" to "running it" or "asking the owner"; reuse is measured. |
| **G3** | **Documentation quality loop.** Missing or stale documentation is detected automatically; owners are nudged politely with a low-effort fix. |
| **G4** | **In-tool help.** Staff using an in-house tool ask questions inside it and get grounded answers from that tool's documentation, with a route to the owner when the bot can't help. |
| **G5** | **Knowledge-gap loop.** Questions the assistant couldn't answer become documentation tasks for the tool's owner. |
| **G6** | **One governed, low-cost engine.** Access control, spend ceilings, evaluation and observability are built once; running cost is kept to the minimum that still meets the quality targets. |

### Guiding principles

1. **Grounded or silent.** Answer from the knowledge base and cite it; otherwise say so and offer a next step. Never invent a capability.
2. **Suggestive, not commanding, except for safety.** Collegial tone; safety warnings stay explicit.
3. **Humans own the content.** AI drafts catalog cards; owners approve them before they're published.
4. **Cheapest thing that meets the bar.** Free tiers, local models, one LLM call per question where possible. Paid components need evidence that the free option fails a quality target.
5. **Keep the door open, don't build the house.** Store a `space_id` on everything so external products can come later, but build no external-customer features now.
6. **Reuse RankUno standards and infrastructure:** the 8-step SDLC, the `project-standards` core, and the existing Supabase, Railway, Sentry and Cloudflare accounts.

---

## 5. Non-goals (for the first releases)

- **External customers or public users.** Revisit only by explicit decision (Q-L06).
- **Running or modifying tools for the user.** The assistant finds and explains; it does not execute.
- **Write actions inside host tools.** The assistant explains and links; actions that change data are a later phase with explicit confirmation (`RiskClass.WRITE`).
- **Replacing GitHub or Drive as storage.** 1Stop indexes and links.
- **General-purpose chat or web search.** Answers are scoped to RankUno tool knowledge.
- **Microsoft sign-in during testing.** Added before rollout beyond the pilot group (see D-21).
- **Languages other than English; voice; mobile apps.**

---

## 6. Constraints

| Area | Constraint | Source |
| :-- | :-- | :-- |
| Process | 8-step SDLC; the Step 3 gate before any production code; ADRs for consequential decisions; README describes only what works. | `project-standards/docs/standards/*` |
| Approval | The AI Lead approves all gates during testing. | Decided 2026-09-30 |
| Budget | **Minimum spend.** Target: existing ~$5/month Railway plus free tiers; LLM usage capped by `CostLedger` (proposed $1/day and $10/month during development, to be confirmed). | Decided 2026-09-30; D-28 |
| Identity | Testing: a Gmail account owns the Drive folder and test services. Later: Microsoft Entra ID for staff sign-in. | Decided 2026-09-30 |
| Registry | Excel master registry in Google Drive. | Decided 2026-09-30 |
| Code | Pydantic v2 `StrictModel`; `BaseTool` pipeline; `CostLedger`; mypy strict; ≥ 85% coverage. | `project-standards` Steps 2, 6, 7 |
| Infrastructure | Supabase Postgres (`ap-south-1`), Railway, Sentry, Cloudflare; Upstash Redis available but optional. | RKN-REC-2026-V1 |
| Scale (initial) | ~50 staff; ≤ 100 tools [Reported, v1]; docs per tool from a handful of files to 50+ (prompt-engine). | v1, observed repos |
| Team | Assumed one AI Lead plus part-time contributors. | [Assumed A-09] |

---

## 7. Success measures (provisional; targets fixed after baselines exist)

| Metric | Definition | Provisional target |
| :-- | :-- | :-- |
| Catalog coverage | Inventoried tools with a published card and ingested docs | ≥ 90% within 3 months of launch |
| Time to find | Median time from first query to opening the right tool card | < 60 s (baseline measured in Phase 1) |
| Retrieval quality | Recall@5 on the golden set (catalog questions and in-tool questions) | ≥ 0.90 |
| In-tool helpfulness | Thumbs-up ÷ rated answers inside tools | ≥ 80% |
| Groundedness | Answer claims supported by a cited source (calibrated judge) | ≥ 95% |
| Correct abstention | "I don't know" when the docs lack the answer | ≥ 90% |
| Owner question load | Questions owners receive directly about their tool (self-reported, monthly) | Falling trend |
| Reuse events | "I used this", owner contacts, repo opens via 1Stop per month | Rising trend |
| Card completeness | Cards passing all mandatory rules | ≥ 80% at 3 months |
| First answer token | Latency | p50 < 1.5 s, p95 < 3 s (a status event within 300 ms) |
| Cost | Total monthly spend (infrastructure + LLM) | As close to the existing ~$5/month as quality allows; hard LLM cap per day |
| Host-tool impact | Embedded loader size; effect on the host tool's page load | < 50 KB gzip; no noticeable slowdown |

---

## 8. Assumptions to validate

| ID | Assumption | Status | Validated in |
| :-- | :-- | :-- | :-- |
| A-01 | Seekers currently rebuild rather than find, often enough to matter. | Open | Phase 1 |
| A-02 | Owners will spend ~15 min reviewing an auto-drafted card. | Open | Phase 1, S-04 |
| A-03 | Tool users want help inside the tool rather than in a separate app. | Open | Phase 1 |
| A-04 | Tool docs are incomplete or stale for tools in development. | Likely (3.7) | Phase 2 readiness audit (S-16) |
| A-05 | Owners get enough repeated questions that deflecting them matters. | Open | Phase 1 |
| A-06 | Hybrid search beats keyword search on RankUno's vocabulary. | Open | Phase 5 (S-05) |
| A-07 | Tool status (alive/deprecated) is unknown today. | Open | Phase 2 inventory |
| A-08 | Owners will act on "top unanswered questions" reports. | Open | Phase 1 |
| A-09 | The team is one AI Lead plus part-time help. | Open | — |
| A-10 | Staff identity is Google Workspace. | **Refuted.** Microsoft Entra ID later; Gmail for testing. | Closed 2026-09-30 |
| A-11 | Utility artifacts live mainly in Drive zips. | **Partly.** The registry is in Drive; the code of the known tools is on GitHub. | Phase 2 inventory |
| A-12 | Free or local models meet the quality targets for most of the work. | Open | S-06, S-15 |
| A-13 | All users of the in-house tools are RankUno staff. | Open, likely | Phase 1 (Q-T03) |

---

## 9. Glossary

| Term | Meaning |
| :-- | :-- |
| **Knowledge space** | An access-controlled collection of knowledge. Release 1 has one: "RankUno internal". The concept exists so external spaces can be added later. |
| **Tool** | A RankUno in-house tool or utility (RAE, prompt-engine, newsletter, …). |
| **Tool card** | The structured catalog entry for one tool: problem, inputs/outputs, how to run, owner, status. |
| **Tool docs** | Everything written about a tool (README, `docs/`, ADRs, guides, `CLAUDE.md`, API spec), ingested and searchable. |
| **Host tool** | An in-house tool with the 1Stop assistant embedded in it. |
| **Source** | Where content comes from: GitHub repo, Drive folder, Excel registry, upload. |
| **Chunk** | A retrievable passage of a document. |
| **Hybrid search** | Keyword search and semantic (vector) search combined, so exact names and meaning both match. |
| **RAG** | Retrieval-augmented generation: find the relevant chunks, then have the model answer from them only. |
| **Criterion (Cₙ)** | One atomic requirement extracted from a seeker's problem. |
| **Grounded answer** | An answer whose claims are supported by cited chunks. |
| **SSO** | Single sign-on: staff log in to 1Stop with their existing company Microsoft account instead of a separate password. |
| **Knowledge gap** | A cluster of questions the assistant couldn't answer well; it becomes a documentation task. |

---

## 10. Document map

| Document | Purpose |
| :-- | :-- |
| [README.md](README.md) | Status and document map. |
| [INVESTIGATION_REPORT.md](INVESTIGATION_REPORT.md) | Findings, review of v1, candidate architecture, the in-tool assistant and minimum-cost design. |
| [docs/investigation/INVESTIGATION_PLAN.md](docs/investigation/INVESTIGATION_PLAN.md) | Phase-by-phase investigation, spikes, gates, delivery roadmap. |
| [docs/investigation/DECISION_LOG.md](docs/investigation/DECISION_LOG.md) | Open and decided design decisions. |
| [docs/investigation/RISK_REGISTER.md](docs/investigation/RISK_REGISTER.md) | Risks and mitigations. |
| [docs/investigation/OPEN_QUESTIONS.md](docs/investigation/OPEN_QUESTIONS.md) | Questions per stakeholder, with answers recorded. |
| [docs/archive/v1/](docs/archive/v1/) | The original v1 documents. |
