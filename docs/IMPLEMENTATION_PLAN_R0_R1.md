# RankUno 1Stop — Implementation Plan: R0 Foundations and R1 Knowledge Base + Web Chat (SDLC Step 4)

| | |
| :-- | :-- |
| **Document ID** | `RKN-1STOP-IMPL-R0R1-V1` |
| **Status** | **APPROVED at Gate G2 on 2026-10-01.** In progress from slice R0.1. |
| **Date** | 2026-10-01 |
| **Implements** | [ARCHITECTURE.md](ARCHITECTURE.md) |

---

## 1. How we build

- **One slice at a time.** Each slice below is a small, reviewable unit: it adds files, tests and docs, passes `scripts/verify.ps1`, and is shown to the owner before the next slice starts.
- **Every slice ends green.** ruff format/check, mypy strict and pytest pass, with coverage ≥ 85% on new code (Step 7). The output is pasted in the slice summary.
- **No network in unit tests.** Integrations are tested against fakes and recorded fixtures; live checks are `@pytest.mark.integration` and run by hand.
- **Spend per slice is stated** and charged through the persisted ledger once it exists (from R0.6).
- **Docs move with code.** Each slice updates the README "what works" section and any affected ARCHITECTURE section (Step 8).
- **Commits.** Semantic messages (`feat(platform): …`), one or more per slice, on a feature branch per slice, merged to `main` once green.

**Inputs needed before a slice can start:**

| Input | Needed by |
| :-- | :-- |
| G2 approval + answers G2-1…G2-6 | R0.1 |
| Supabase project or schema (G2-2) + connection string | R0.12 (local Docker Postgres until then) |
| Gmail app password for the test account | R0.8 |
| Ollama installed on the laptop with one small model pulled (ADR 0008) | R0.10 live check (unit tests use fakes) |
| Paid LLM key (Haiku 4.5 or Gemini Flash, no-training tier) | R1 real-doc quality check; deployed pilot |
| Docker Desktop installed (not on this machine yet) **or** the Supabase project created early | R0.4 test database |
| GitHub read-only token (Q-I05) | R1.3 |
| Drive folder shared with the service account (Q-A02) | R1.2 |
| List of tools + pilot (Q-T01) | R1.8 onward (real data); fixtures until then |

---

## 2. R0 Foundations

**Goal:** a deployed, secured, observable skeleton. A staff member can log in and get a streamed (placeholder) reply; every LLM call is capped and recorded.
**Spend:** $0 (the live LLM smoke test uses the local Ollama model).

### R0.1 Repository scaffold
| File | Content |
| :-- | :-- |
| `.gitignore`, `.editorconfig` | From project-standards; adds `web/node_modules`, `web/dist`, `.env*` (except `.env.example`) |
| `pyproject.toml` | Package `onestop`. *As built:* only pydantic, pydantic-settings and tenacity at R0.1; each further dependency is added in the slice that first uses it, so it is reviewed with its code. Planned deps: fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy[asyncio], psycopg[binary], alembic, pgvector, httpx, tenacity, python-json-logger, sentry-sdk, itsdangerous; dev: pytest, pytest-asyncio, pytest-cov, ruff, mypy, import-linter, respx. ruff/mypy config copied from project-standards. |
| `.importlinter` | Contract: `src.core` ↛ `src.integrations`/`src.modules`; `src.integrations` ↛ `src.modules` |
| `scripts/verify.ps1`, `Makefile` | ruff format --check, ruff check, mypy, lint-imports, pytest --cov |
| `.github/workflows/ci.yml` | The same checks plus gitleaks on the repo |
| `.env.example` | Every variable in ARCHITECTURE §13, no values |
| `README.md` | "What works" section (initially: nothing runnable) |

**Done when:** `git init`, first commit, CI green on an empty test suite.

### R0.2 Copy the governed core (ADR 0001)
| File | Content |
| :-- | :-- |
| `src/core/*`, `tests/core/*` | Copied verbatim from `project-standards` (not `integrations/semrush.py`) |
| `docs/adr/0001-reuse-project-standards-core.md` | Already drafted |
**Done when:** the copied core tests pass under this repo's CI.

### R0.3 Settings
| File | Content |
| :-- | :-- |
| `src/modules/platform/settings.py` | `OneStopSettings` (pydantic-settings) for ARCHITECTURE §13, all secrets `SecretStr`; production boot refuses missing secrets |
| `tests/modules/platform/test_settings.py` | Missing-secret refusal in production; defaults in development |

### R0.4 Database and migration 0001
| File | Content |
| :-- | :-- |
| `docker-compose.yml` | `pgvector/pgvector:pg16`, port 5432, named volume |
| `alembic.ini`, `migrations/env.py` | Async Alembic, schema `onestop` |
| `migrations/versions/0001_platform.py` | Extensions (`vector`, `pg_trgm`, `citext`, `pgcrypto`); tables `spaces` (seed `internal`), `users`, `login_codes`, `sessions`, `llm_calls`, `jobs`, `schedules`, `rate_limits`, `email_deliveries`, `audit_log`, `settings_kv` |
| `src/modules/platform/db.py` | Async engine/session factory; `transaction()` helper |
| `src/modules/platform/tables.py` | SQLAlchemy Core `Table` definitions mirroring the migration |
| `tests/conftest.py` | Spins up a test database (Compose or `TEST_DATABASE_URL`), runs migrations once, wraps each test in a rolled-back transaction |
| `tests/modules/platform/test_migration.py` | Upgrade → downgrade → upgrade is clean; tables and indexes exist |

### R0.5 Audit log and rate limits
| File | Content |
| :-- | :-- |
| `src/modules/platform/audit.py` | `record(actor, action, target, detail)` |
| `src/modules/platform/rate_limit.py` | Fixed-window `check_and_increment(key, limit, window)` in one SQL upsert |
| Tests | Limits enforced; window rollover; concurrent increments are counted correctly |

### R0.6 Persisted spend guard (D-28)
| File | Content |
| :-- | :-- |
| `src/modules/platform/spend.py` | `PersistedSpendGuard`: `reserve(estimate)`, `record(call)`, `status()`; day/month sums from `llm_calls`; advisory lock; kill switch; threshold alerts queued as jobs |
| `src/integrations/llm/pricing.py` | Dated price table per model; unknown model → `ConfigurationError` |
| Tests | Under cap passes; over day cap / month cap refuses; concurrent reservations can't jointly overshoot; restart (new guard instance) keeps the totals; kill switch blocks |

### R0.7 Jobs and scheduler (D-19, spike S-12)
| File | Content |
| :-- | :-- |
| `src/modules/platform/jobs.py` | `enqueue(kind, payload, idempotency_key, run_after)`, `claim()` with `SKIP LOCKED`, `complete/fail` with backoff, stale-lock recovery, handler registry |
| `src/modules/platform/scheduler.py` | Loop that reads `schedules`, enqueues due jobs exactly once (`idempotency_key = name:period`) |
| `src/modules/platform/worker.py` | Async worker loop; graceful shutdown |
| Tests | Two workers never run the same job; a crash mid-job is re-run after lock expiry; an idempotent enqueue doesn't duplicate; a schedule fires once per period across restarts |

### R0.8 Email (D-20)
| File | Content |
| :-- | :-- |
| `src/integrations/email/base.py` | `EmailSender` Protocol, `EmailMessage` model |
| `src/integrations/email/smtp_gmail.py` | SMTP over STARTTLS with an app password; retry; rate-limit key `smtp.gmail` |
| `src/modules/platform/mailer.py` | Idempotent send via `email_deliveries`; plain-text + simple HTML templates (login code, spend alert) |
| Tests | Same idempotency key sends once; failure recorded; fake sender in tests; one manual integration test sends to the admin |

### R0.9 Authentication (D-21)
| File | Content |
| :-- | :-- |
| `src/modules/platform/auth.py` | Request code (allowlist check, hashed code, uniform response), verify (attempts, expiry), sessions (create/lookup/revoke), CSRF token |
| `src/modules/api/deps.py` | `current_user`, `require_admin`, CSRF dependency |
| `src/modules/api/routes_auth.py` | `/auth/request-code`, `/auth/verify-code`, `/auth/logout`, `/me` |
| `src/modules/api/routes_admin_users.py` | List/add/deactivate users |
| Tests | Unknown email gets the same response as a known one; wrong code ×5 locks; expired code fails; logout revokes; staff can't reach admin routes; CSRF required on POST |

### R0.10 LLM provider abstraction (provisional: S-15)
| File | Content |
| :-- | :-- |
| `src/integrations/llm/base.py` | `LLMProvider` Protocol: `stream(messages, max_tokens, temperature) -> AsyncIterator[Delta]`, `count_tokens()`, final usage |
| `src/integrations/llm/ollama_adapter.py` | Development provider (ADR 0008): Ollama's OpenAI-compatible streaming endpoint; usage from the response; priced $0 |
| `src/integrations/llm/anthropic_adapter.py` **or** `gemini_adapter.py` | Paid pilot provider; built when the pilot needs it (R1 quality check at the latest) |
| `src/modules/assistant/llm_tool.py` | `AnswerLLMTool(BaseTool)`: `RiskClass.FINANCIAL`; reserve → call → record in `llm_calls` |
| Tests | Fake provider: tokens stream; usage recorded with cost; cap refusal yields `cap_reached`; provider error → recorded failure, no charge beyond reported usage |

### R0.11 API app, SSE skeleton, observability
| File | Content |
| :-- | :-- |
| `src/modules/api/app.py` | FastAPI app factory; lifespan starts the worker and scheduler; Sentry; JSON logging with `trace_id`; error handler (no stack traces to clients); SPA static hosting |
| `src/modules/assistant/events.py` | SSE event models v1 (ARCHITECTURE §8.3) + encoder |
| `src/modules/api/routes_chat.py` | `POST /api/v1/chat`: auth, rate limit, `status` → placeholder answer via `AnswerLLMTool` (no retrieval yet) → `done` |
| `src/modules/api/routes_admin_spend.py`, `routes_admin_jobs.py` | Caps, kill switch, usage by day/purpose; job list |
| `src/cli.py` | `onestop serve | migrate | worker | sync-now` entry points |
| Tests | SSE event order and shapes; cap_reached path; health endpoint reveals nothing internal |

### R0.12 Web shell (G2-1)
| File | Content |
| :-- | :-- |
| `web/` (Vite + React + TS) | Pages: Login (email → code), Chat (SSE client, streamed text), Admin › Spend, Admin › Users, Admin › Jobs |
| `web/src/api/` | Types generated from `/openapi.json` (`openapi-typescript`), SSE client with typed events |
| `scripts/gen-types.mjs` | Type generation with a committed snapshot for CI |
| Tests | Vitest: SSE parser handles every event type; login flow happy and error paths |

### R0.13 Container and deployment (S-13)
| File | Content |
| :-- | :-- |
| `Dockerfile` | Multi-stage; gitleaks pinned with checksum; embedding model pre-download stage prepared (used in R1) |
| `railway.json` | Build/start commands, health check |
| `docs/DEPLOY.md` | Railway + Supabase setup, variables, migration on deploy, rollback |
| Check | Deployed; login works; p95 first event < 300 ms and first placeholder token < 3 s from India; idle monthly cost noted |

**R0 exit criteria**
- [ ] Deployed on Railway against Supabase; owner logs in with an emailed code.
- [ ] Placeholder chat streams; one live LLM call is recorded in `llm_calls` with its cost.
- [ ] Caps proven: a test cap of $0.001 blocks the next call with `cap_reached`; the totals survive a redeploy.
- [ ] Jobs survive a restart without loss or duplication (S-12 passed).
- [ ] CI green; coverage ≥ 85%; README "what works" updated.

---

## 3. R1 Knowledge base + web chat

**Goal:** real tool docs ingested safely, searchable with hybrid search, answered with citations in the web app; tool cards drafted and approved; handover FAQs captured.
**Spend:** ≤ $5 (card drafting for the first tools + a judged eval run), within the caps.

### R1.1 Migration 0002: knowledge tables
`migrations/versions/0002_knowledge.py` creates `tools`, `sources`, `documents`, `document_versions`, `chunks` (HNSW + GIN + trigram indexes; generated `fts`), `tool_cards`, `handover_answers`, `quarantine_items`, `registry_snapshots`, `conversations`, `messages`, `citations`, `feedback`, `answer_cache`. `tables.py` updated.
**Tests:** migration round-trip; a generated `fts` column populates; vector index used (`EXPLAIN` check in an integration test).

### R1.2 Google Drive registry (S-01, S-02)
| File | Content |
| :-- | :-- |
| `src/integrations/gdrive/client.py` | Service-account auth from the base64 env; `get_start_token`, `list_changes(token)`, `find_file(folder, name)`, `download(file)`; Sheets export as `.xlsx` |
| `src/modules/ingestion/registry.py` | `.xlsx` → `RegistryRow[]` with a configurable column map; issues per row; snapshot; upsert `tools` by `row_key` |
| Tests | Fixture workbook with missing/extra columns and empty cells; incomplete rows kept with issues; unchanged token → no download |
| Spike report | `docs/investigation/spikes/S-01_S-02.md`: access scope proven; row count, columns, completeness of the real registry |

### R1.3 GitHub client
| File | Content |
| :-- | :-- |
| `src/integrations/github/client.py` | `latest_commit(repo, branch)`, `tree(repo, sha)`, `blob(repo, path, sha)`; rate-limit key `github.api`; retries; size limits |
| Tests | `respx`-recorded fixtures; 404/403 handling; size limit enforced |

### R1.4 Secret gate (S-03)
| File | Content |
| :-- | :-- |
| `src/integrations/secretscan/gitleaks.py` | Run `gitleaks detect --no-git --report-format json` on a temp dir; parse findings to path/rule/line **only**; missing binary or non-zero error → `SecretScanUnavailable` (fail closed) |
| `src/modules/ingestion/secret_gate.py` | Filter files; create `quarantine_items`; audit; admin email (paths only) |
| `src/modules/api/routes_admin_quarantine.py` + web page | List and resolve (resolution = owner fixed it upstream; the next sync re-scans) |
| Tests | Planted fake AWS key, private key, `.env` → quarantined, never chunked; scanner missing → whole sync aborts; finding values never appear in DB, logs or email |
| Spike report | `S-03.md`: run over the real repos; hits by repo; false-positive notes; runtime |

### R1.5 Document typing and `1stop.yaml`
| File | Content |
| :-- | :-- |
| `src/modules/ingestion/onestop_yaml.py` | Parse/validate `OneStopYaml`; glob matching for include/exclude/authoritative/restricted |
| `src/modules/ingestion/doc_types.py` | Path/content rules → `DocType`; ADR status parser; title and `doc_date` extraction (front-matter, `Date:` lines, else commit date) |
| Tests | Table-driven: prompt-engine ADR samples (Accepted / Superseded / Amends), loc-intel status-note names, `CLAUDE.md`, OpenAPI |

### R1.6 Chunker
| File | Content |
| :-- | :-- |
| `src/modules/ingestion/chunker.py` | Markdown heading splitter with token targets and overlap; ADR section splitter; OpenAPI operation splitter; heading path prefix |
| Tests | Golden outputs for sample docs; no chunk exceeds max; code blocks never split mid-block |

### R1.7 Local embeddings (S-06)
| File | Content |
| :-- | :-- |
| `src/integrations/embeddings/base.py`, `fastembed_local.py` | `Embedder` Protocol; lazily loaded model; batch embed; model name exposed |
| Dockerfile | Model pre-downloaded at build time |
| Tests | Fake embedder in unit tests; one integration test checks dimension 384 and determinism |
| Spike report | `S-06.md`: memory and CPU on Railway; quality vs one alternative on the golden set |

### R1.8 Ingestion pipeline and weekly sync (D-06)
| File | Content |
| :-- | :-- |
| `src/modules/ingestion/pipeline.py` | `sync_source(source_id)` implementing ARCHITECTURE §6.1 steps 1–10, transactional version swap |
| `src/modules/ingestion/sync.py` | `sync_registry` job; `weekly_sync` schedule (Sunday 02:00 IST); admin `sync now` (all or one source) |
| `src/modules/api/routes_admin_sync.py` + web page | Trigger + last-sync status per tool |
| Tests | Unchanged commit → zero work; changed file → new version, old chunks inactive atomically; deleted file → inactive; quarantined file skipped; rerun is idempotent |

### R1.9 Hybrid retrieval (S-05)
| File | Content |
| :-- | :-- |
| `src/modules/retrieval/hybrid.py` | The SQL in ARCHITECTURE §7.2, parameterised; access filters in every branch |
| `src/modules/retrieval/ranking.py` | Scope/authority/type/supersession/recency weighting (§7.3); per-document cap |
| Tests | Fixture corpus: exact-name queries hit by trigram; paraphrases hit by vector; a restricted chunk is never returned to staff; scope boost works |

### R1.10 Evaluation harness
| File | Content |
| :-- | :-- |
| `eval/sets/catalog.jsonl`, `eval/sets/in_tool.jsonl` | Seed sets: fixture questions now; real questions from the owner/users as they arrive |
| `eval/run.py` | Retrieval metrics (recall@5, MRR, p95) at $0; optional judged answers with `--max-spend` |
| CI | Retrieval eval on the fixture corpus; fails on regression beyond tolerance |
| Spike report | `S-05.md`: FTS-only vs vector-only vs hybrid vs weighted on real docs |

### R1.11 Tool cards, review and handover (S-04, D-29)
| File | Content |
| :-- | :-- |
| `src/modules/catalog/extract.py` | Deterministic facts from manifests: stack, runtime, entry points |
| `src/modules/catalog/draft.py` | `DraftCardTool(BaseTool, FINANCIAL)`: one structured call → `ToolCard` + `CardFieldEvidence`; schema-validated; retry once on invalid JSON |
| `src/modules/catalog/review.py` | States draft → in_review → published; signed review link for the author (expires in 14 days); publishing writes a `card` document and indexes it |
| `src/modules/catalog/handover.py` | The handover questionnaire (P4.8) → `handover_answers` → `faq` documents |
| API + web pages | Card review/edit form, evidence shown per field, handover form, published card page |
| Tests | Invalid LLM output rejected; an unapproved card is not retrievable; publish indexes the card; a handover answer becomes a searchable FAQ |
| Spike report | `S-04.md`: author scores per field and review time for the first tools |

### R1.12 Answer pipeline
| File | Content |
| :-- | :-- |
| `src/modules/assistant/prompts/answer_v1.md`, `persona_web_v1.md` | Versioned prompts (ARCHITECTURE §8.2) |
| `src/modules/assistant/answer.py` | Steps 1–10 of §8.1: cache, retrieve, early abstain, guard, stream, citation post-check, persist |
| `src/modules/assistant/citations.py` | `[n]` parser, mapping, unknown-marker stripping |
| `src/modules/assistant/cache.py` | Key building, invalidation on new versions |
| `src/modules/api/routes_chat.py` | Placeholder replaced; conversation history endpoints; feedback endpoint |
| Housekeeping job | Delete message content older than 180 days (D-23); keep the database awake (R-25) |
| Tests | Low-score question abstains with no LLM call; citations map to the chunks supplied; injected "ignore instructions" text inside a doc doesn't change behaviour (fake LLM asserts the delimiting); cache hit costs $0; cap reached returns sources |

### R1.13 Web chat UI
| File | Content |
| :-- | :-- |
| `web/src/pages/Chat.tsx` + components | Streamed answer, citation chips (tool, doc, section, date) opening the source, abstain panel with suggested tools and "ask the maintainer", thumbs up/down with reason |
| `web/src/pages/Tools.tsx`, `ToolDetail.tsx` | Browse published cards; filter chat by tool |
| `web/src/pages/admin/*` | Sync, quarantine, cards review, spend (already from R0) |
| Markdown | Sanitised renderer: no raw HTML, no images, link allowlist |
| Tests | Vitest for rendering safety (script/img/link cases) and event handling |

### R1.14 Security pass (S-11 subset)
| File | Content |
| :-- | :-- |
| `tests/redteam/` | Injection in a README and a `CLAUDE.md`; system-prompt extraction attempts; markdown exfiltration; restricted-doc access by staff; oversized input. Fake-LLM structural tests in CI; a small live run (≤ $0.50) before the R1 exit |
| `docs/security/STEP5_R1.md` | The 8 Step 5 answers, updated with reality |

### R1.15 Docs drift and R1 review
README "what works" and run instructions; ARCHITECTURE updated to as-built; ADRs for anything decided during R1; risk register refreshed; spike reports linked.

**R1 exit criteria**
- [ ] ≥ 60% of the inventoried tools ingested; 0 secrets in the index (S-03).
- [ ] recall@5 ≥ 0.90 on both golden sets with the free configuration, or a recorded decision to pay for one component (D-28).
- [ ] Groundedness ≥ 95% on the judged sample; abstention behaves on no-answer questions.
- [ ] ≥ 3 tool cards published after author review; ≥ 1 handover completed and passing the non-author check (8/10).
- [ ] Spend for R1 ≤ $5 and inside the caps; usage visible by purpose.
- [ ] CI green; coverage ≥ 85%; red-team subset passing; docs current.

---

## 4. Order and estimate

```
R0.1 → R0.2 → R0.3 → R0.4 → R0.5 → R0.6 → R0.7 → R0.8 → R0.9 → R0.10 → R0.11 → R0.12 → R0.13
                                                                                            │
R1.1 → R1.5 → R1.6 → R1.7 → R1.3 → R1.4 → R1.8 → R1.9 → R1.10 → R1.12 → R1.13 → R1.11 → R1.14 → R1.15
              (R1.2 slots in whenever the Drive folder is shared)
```

| Release | Slices | Estimate (one person, ~70%) |
| :-- | :-- | :-- |
| R0 | 13 | ~2 weeks |
| R1 | 15 | ~3 weeks |

The parsing, chunking and retrieval slices (R1.5–R1.7, R1.9) work on fixtures, so they don't wait for the GitHub token or the Drive share.
