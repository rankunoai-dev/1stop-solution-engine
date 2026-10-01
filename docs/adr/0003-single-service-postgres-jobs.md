# ADR 0003 — One Railway service; jobs and schedules in Postgres

**Status**: Accepted (Gate G2, 2026-10-01) · **Decision log**: D-18, D-19, D-22

## Context
~50 users, weekly sync, minimum spend. v1 proposed separate frontend, backend, Celery worker and Celery Beat containers, plus Redis.

## Decision
- One Railway service runs the FastAPI API, a worker loop and a scheduler loop (asyncio tasks started at app startup). The same image can run `onestop worker` separately later without code changes.
- Jobs live in a Postgres `jobs` table claimed with `FOR UPDATE SKIP LOCKED`, with idempotency keys, retries with backoff and stale-lock recovery. Schedules live in a `schedules` table.
- LLM traces and spend share one `llm_calls` table; errors go to Sentry free.
- The React SPA is built into the image and served by FastAPI.

## Alternatives considered
- Celery + Upstash: broker polling on a per-command-priced Redis; more moving parts.
- Separate frontend service: extra cost; no SSR need for an internal app.

Chat history is stored in Postgres (`conversations`, `messages`) behind a `ConversationStore` interface. Redis was considered for chat context and rejected at Gate G2 (G2-7): Postgres is already durable and fast enough at this scale; a Redis cache can be added behind the interface if a slowdown is measured.

## Consequences
Lowest possible running cost (the existing ~$5 Railway plan). A long ingestion job shares CPU with the API; acceptable at weekly cadence, and revisited if latency suffers during sync (S-13).
