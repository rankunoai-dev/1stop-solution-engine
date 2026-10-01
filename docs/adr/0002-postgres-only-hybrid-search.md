# ADR 0002 — Postgres-only hybrid search with local embeddings

**Status**: Accepted (Gate G2, 2026-10-01); embedding model and weights Provisional (S-05, S-06) · **Decision log**: D-07, D-08, D-09, D-10

## Context
≤ 100 tools and a few thousand doc pages; minimum spend (D-28); answers must find both exact identifiers (tool names, error codes) and paraphrases.

## Decision
- Supabase Postgres with `pgvector` (HNSW, cosine), weighted `tsvector` full-text search and `pg_trgm`, fused by Reciprocal Rank Fusion in one SQL statement (ARCHITECTURE §7.2).
- Embeddings computed locally with `fastembed` (`BAAI/bge-small-en-v1.5`, 384 dims) on CPU inside the service.
- No separate vector DB, no reranker, no Redis.

## Alternatives considered
- Qdrant: an extra service and cost; no evidence it's needed at this scale.
- Hosted embeddings: per-token cost, and content leaves RankUno infrastructure.
- Reranker: extra latency and cost; added only if S-05 shows a ≥ 0.03 recall@5/MRR gain.

## Consequences
One database to secure and back up; metadata and vectors are transactionally consistent. `embedding_model` is stored per chunk, so switching models is a re-embed job. If S-05/S-06 miss their targets, the upgrade order is: paid embedding model → local reranker → Qdrant.
