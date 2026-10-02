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
| D-21 | Staff sign-in | **DECIDED (staged)** | Allowlisted email login while testing; Microsoft Entra ID before rollout — OTP+session layer implemented in R0.9 | Owner |
| D-22 | LLM observability | PROPOSED | Postgres `llm_trace` table + Sentry free | P10 |
| D-23 | Conversation retention | PROPOSED | 180 days content, aggregates kept; confirm with owner | P9 |
| D-24 | Web-search fallback | PROPOSED | Off | P6 |
| D-25 | When the bot can't answer | PROPOSED | "Ask the maintainer" (pre-filled message) + gap list; answers become FAQs | P7 |
| D-26 | Reuse of project-standards core | PROPOSED | Copy `src/core` verbatim (prompt-engine ADR 0001) | P10 |
| D-27 | Access isolation | PROPOSED | App-level `space_id`/`restricted` checks now; Postgres RLS when a second space appears | P3 |
| D-28 | Cost posture | **DECIDED** 2026-09-30, extended 2026-10-01 | Minimum spend; costs kept low throughout initial development; caps proposed: $1/day and $10/month LLM (awaiting owner's numbers, Q-L07) | Owner |
| D-29 | Tool ownership model | **DECIDED** 2026-09-30 | Author needed only for the onboarding handover; maintainer (default: admin) afterwards | Owner |
| D-30 | Partial-match threshold for the DIY bridge | PROPOSED | Offer the DIY pathway at 40–80% match; below 40% = honest "no match"; above 80% = use it as-is | — |
| D-31 | Adaptability classifier — what counts as "bridgeable" | PROPOSED | LLM judge call (purpose=`judge`) with a rubric: only prompt/config changes, no new integrations, structural code changes capped at ~10 lines | — |
| D-32 | Prompt card structure | PROPOSED | Five-section card: Context → Gap → What NOT to touch (guardrails + security) → The ask → Verification checklist | — |
| D-33 | Upload-back mechanism | PROPOSED | Start with file upload to a `/api/v1/tools/evaluate` endpoint; GitHub link import added later (R3) | — |
| D-34 | Installation/run guide for full matches | PROPOSED | Template-first (OS steps, Docker, Claude Code import); LLM-expanded only if the template can't cover the tool's requirements | — |

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

### D-30 Partial-match threshold for the DIY bridge
- **Context (owner, 2026-10-01):** When the best-matching tool only partially solves a user's problem, the engine should decide whether a non-technical person can close the gap themselves rather than giving up.
- **Three outcome states:**
  1. **Match score > 80%** → "Use it as-is" pathway; provide an installation/run guide (D-34).
  2. **Match score 40–80%** → "DIY bridge" pathway; judge adaptability (D-31), then generate a prompt card (D-32) and end-to-end guidance in the chat window.
  3. **Match score < 40%** → Honest no-match: "No RankUno tool solves this right now"; surface the gap to the maintainer (D-25).
- **Evidence needed:** The thresholds 40% and 80% are initial guesses; the golden-set evaluation in R1.10 will tell us the real score distribution so we can set these empirically. Record calibrated values in this entry once S-05 data exists.

### D-31 Adaptability classifier — what counts as "bridgeable"
- **Context:** Not every gap is closable by a non-technical person. The engine must judge before offering the DIY pathway, to avoid setting people up to fail.
- **Proposed rubric (one LLM `judge` call):**
  - BRIDGEABLE if: the gap is one prompt string, one config value, one flag, or one small input/output format change (≤ ~10 lines of code equivalent).
  - NOT BRIDGEABLE if: the gap requires a new integration, a new dependency, an API key the user doesn't have, or structural code changes beyond the rubric.
- **Output:** `{bridgeable: bool, complexity: "prompt_only" | "config" | "code_small" | "too_complex", plain_english_explanation: str}`.
- **Cost:** one `judge`-purpose LLM call per partial-match question. Acceptable because partial matches are less frequent than exact answers.

### D-32 Prompt card structure
- **Context:** The generated prompt card is what the user takes to Claude Code (or any AI tool) together with the existing tool's files. It has two audiences: (1) the person physically moving the files who may have no interest in what is inside them, and (2) the AI that will actually read and act on the content. The card must serve both without either audience having to ask for clarification.

**Design principles (updated owner direction, 2026-10-02):**
- The card is a contract, not a conversation. It is generated once and handed to the user intact; neither the user nor the AI should need to ask for clarification.
- **No IDE Required:** Non-technical analysts do NOT need to install or know how to use an IDE (like VS Code or CLI tools). The workflow works entirely inside **Claude Web Chat / Claude Cowork** (browser-based) by uploading `.zip` or `SKILL.md` files directly.
- The AI-facing sections include embedded self-chaining checkpoints — prompts the AI generates *for itself* at each stage of its work. The engine generates these checkpoints specifically for the tool and change at hand (not generic advice), so the AI reasons correctly without a human steering it mid-task.
- The analyst-facing section (Part A) uses only plain, polite action words: "go to", "download", "open", "attach", "copy", "paste", "wait", "save", "zip", "upload". No word that requires knowing what the tool does.

**Two-part structure:**

**PART A — Steps for the person handling this today (No IDE or coding needed)**
_(This is the only section the person moving the files needs to read. Works in Claude Web Chat, Claude Cowork, or Claude Code CLI.)_

Numbered steps, generated specifically for the tool (file name, folder structure, upload destination filled in by the engine):

  1. Go to [tool download link or folder path the engine fills in]. Download the `.zip` file or `SKILL.md` document to your computer (e.g. your Desktop).
  2. Open **Claude Web Chat** (claude.ai), **Claude Cowork**, or your preferred AI chat assistant in your browser.
  3. Click the paperclip / attachment icon and upload the `.zip` or `SKILL.md` file you downloaded in Step 1.
  4. Copy everything inside the box labelled **PART B** below — from the first line to the last — and paste it into the chat message box. Do not add or remove anything.
  5. Press Enter and wait for the AI to process your request and generate the updated tool files / `.zip`. This usually takes 1–3 minutes.
  6. Download the updated `.zip` file or modified files provided by the AI back to your computer.
  7. Go to [1Stop upload page URL the engine fills in]. Click "Upload modified tool." Drag your modified `.zip` file into the upload area (or click "Choose file" and find it). Click "Submit."
  8. Wait for the score to appear. If the bar turns green and says 80% or above, your work here is done! If it is below 80%, a message will tell you what to do next.

**PART B — Paste this into Claude Web Chat / Claude Cowork / AI Assistant (do not change anything below this line)**
_(The person handling this does not need to read or understand Part B.)_

  1. **Tool snapshot** — what the tool currently does, which files belong to it, and which file is the main entry point. Generated from the tool card (2–4 sentences). Gives the AI a grounded starting point before it reads any code.

  2. **What needs to change** — the single, concrete, minimal ask. One sentence: what feature or behaviour is missing and exactly what form the addition should take. Combined with the gap analysis (how the tool currently falls short). Example: "Add a `--max-lines N` flag to the existing `run` command so it stops printing after N lines; N must be a positive integer; default is unlimited."

  3. **Boundaries — what must not move** — the explicit DO NOT list, always present and never condensed:
     - Do not change any existing authentication or login flow.
     - Do not add calls to any outside service or API that is not already in the code.
     - Do not rename or remove any existing command, flag, or setting that users already rely on.
     - Do not delete or weaken any existing test.
     - Do not add dependencies that require a paid licence.
     - *(Engine appends tool-specific rules here based on the tool card's `guardrails` field.)*

  4. **Your own reasoning checkpoints** — self-chaining prompts the AI must work through before touching any file:
     - *Before starting:* "Which files do I need to read first to understand the current structure? Name them, then read them before writing a single line."
     - *After reading:* "Write the change in one sentence. Does it stay within all the boundaries above? If not, stop and say why."
     - *While implementing:* "After each file I edit, ask: have I introduced anything the boundaries forbid? If yes, revert that file and find a different path."
     - *Before declaring done:* "Go through the verification items in section 5 one by one. If any item fails, fix it before finishing."
     - *(Engine replaces the italic text above with tool-specific versions: e.g., "Which files do I need to read first?" becomes "Read `src/cli.py`, `src/runner.py`, and `README.md` before making any changes." The engine generates these from the tool card's file list and the ask.)*

  5. **How to know it worked** — the verification checklist the AI must pass before finishing:
     - *(Engine generates 3–5 concrete, runnable checks specific to the ask. Example:* `python tool.py run --max-lines 5` *outputs exactly 5 lines and exits without error.)*
     - Each check is one command or one observation. No check requires building a full test suite.

  6. **Update the docs** — always the final step, never optional:
     > "Open `README.md` in the tool's root folder. Add or update one paragraph that describes what the tool now does, including the change you just made. If a file named `1stop.yaml` exists, add the new capability to the `capabilities` list. Save both files. They must be present in the folder before the zip in Part A Step 7 is created."
     This step is non-negotiable. Without updated docs, the re-evaluation in D-33 reads stale capability declarations and gives an incorrect score.

- **LLM purpose:** `card_draft` (already in `llm_calls.purpose` constraint).
- **Engine generation note:** The engine fills in all italicised and bracketed placeholders when generating the card. The final card delivered to the user contains no placeholders — every instruction is specific to the exact tool and change. Part A step numbers and Part B checkpoint text are generated together in the same `card_draft` call so they are consistent.

### D-33 Upload-back mechanism
- **Context:** After the user modifies a tool with the prompt card, they should be able to return it to 1Stop for re-evaluation, creating a closed loop: "Did I fix my original problem?"

**How the re-evaluation works (owner clarification 2026-10-02):**

Running the full modified source through an LLM would cost $0.05–$0.50 per upload and is unreliable. Instead, the re-evaluation operates on **declared capabilities** — the same signal the original retrieval used — extracted statically from the modified tool:

| File | What we extract | Cost |
| :-- | :-- | :-- |
| `README.md` / `README.rst` | What the tool says it does | 0 |
| `1stop.yaml` (if present) | Structured capability declaration | 0 |
| CLI flag definitions (argparse/click/typer) | AST parse only, no execution | 0 |
| OpenAPI spec (if present) | Endpoint + description list | 0 |

Total extracted text: < 1000 tokens.  Then:
1. **Embed** the extracted description (local model, free).
2. **Re-run hybrid search** — compare the new embedding against the user's original query embedding (same pipeline as the original search).
3. **Optional `judge` call** (< 200 tokens, ~$0.0001): "Does this capability description solve the original problem? Yes/No + confidence."

The score that comes back is the re-evaluation score.

- **Proposed flow:**
  1. User uploads the modified file (or a zip) to `POST /api/v1/tools/evaluate`.
  2. A `jobs` record is created (kind=`evaluate_uploaded_tool`, payload includes the original problem statement and query embedding).
  3. The worker extracts capability text (README, AST parse of CLI flags), embeds it, re-runs the match score.
  4. The result is shown in the chat window: "Your modified tool now matches X% of your requirement."
  5. If score > 80%, offer to formally ingest the tool into the knowledge base (admin approval required).
- **Security requirements** — the upload endpoint must:
  - Accept only specific file extensions (`.py`, `.ts`, `.js`, `.md`, `.yaml`, `.json`, `.zip`).
  - Never execute uploaded code; use `ast.parse()` for Python and text grep for others — parse only.
  - Store files in a temp directory isolated from the source tree; delete after the job completes or after 1 hour.
  - Rate limit: 3 evaluations per user per day (enforced via `rate_limits` table, R2.5).
- **Later (R3):** Accept a GitHub repository URL instead of a file upload.

### D-34 Installation/run guide for full matches
- **Context:** Even when a tool is a perfect match, a non-technical user may not know how to run it. The response should include a complete, OS-aware, end-to-end guide.
- **Proposed approach:** Template-first, LLM-expanded.
  - The tool card's `stack` and `entry_points` fields (from R1.11) drive a template: "This tool runs with Python 3.11+. Steps: 1) Install Python… 2) Open a terminal… 3) Run `python tool.py …`"
  - If the tool card also says it runs inside Claude Code (CLAUDE.md detected), add: "In Claude Code: open the folder, run `/import`, then …"
  - If the template doesn't cover the tool's requirements (non-standard stack, Docker, unusual setup), one `card_draft`-purpose LLM call fills the gaps.
- **Tone guidance:** step-by-step, numbered, no assumed knowledge. Every step is one action. The guide ends with a "you should see:" verification line.

### D-29 Tool ownership model — DECIDED
- **Decision (owner, 2026-09-30):** Once a tool is onboarded, its original owner is not needed.
- **Model:** two roles per tool.
  - **Author:** the person who built it. Needed once, for the **onboarding handover** (card review + handover questionnaire, INVESTIGATION_PLAN P4.8). Optional after that.
  - **Maintainer:** receives unanswered questions, thumbs-down answers and doc reminders, and approves card changes. Defaults to the **platform admin (AI Lead)** after handover. For a tool still in active development, the developer currently changing it stays the maintainer until the tool is marked stable (Q-A06).
- **Consequences:**
  1. Onboarding must capture the author's tacit knowledge (common questions, gotchas, error fixes, which docs are current) as FAQ documents, because afterwards nobody may be able to answer.
  2. Leavers need no special process: the registry keeps the author for history; routing uses the maintainer field.
  3. Digests for stable tools all go to the admin, concentrating load on one person (R-20, R-28). The gap loop (answer once, then it becomes an FAQ) keeps that load small.
