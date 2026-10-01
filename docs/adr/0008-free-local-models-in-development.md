# ADR 0008 — Free local LLM in development; cheap paid model only where needed

**Status**: Accepted (Gate G2 amendment G2-4, 2026-10-01) · **Decision log**: D-11, D-28 · **Risk**: R-24

## Context
The owner wants free models during development. The development laptop has 32 GB RAM, a 14-core i7-13650HX and an RTX 4050 Laptop GPU (6 GB), which can run small open models (3–8B parameters, quantised) locally. Free hosted tiers may use inputs to improve the provider's models, so they cannot receive real internal docs.

## Decision
| Stage | Model | Cost |
| :-- | :-- | :-- |
| Development and tests on the laptop | Open model via **Ollama** (OpenAI-compatible local endpoint); exact model chosen in S-15 | $0; data never leaves the machine |
| Fake/fixture docs only (optional) | Gemini free tier | $0 |
| Quality checks on real docs; deployed pilot on Railway | Claude Haiku 4.5 or Gemini Flash on a paid, no-training tier | Cents, inside the $1/day and $10/month caps |

- The first LLM adapter built (R0.10) is the **Ollama** adapter; the paid adapter follows when the pilot needs it.
- Local models are priced at $0 in `pricing.py` but still recorded in `llm_calls` (tokens, latency), so usage stays visible.
- The provider is chosen per environment by `LLM_PROVIDER` / `LLM_MODEL`.

## Consequences
Development costs nothing. Answer quality from a small local model is lower than Haiku's; S-15 measures the gap on the golden set, and the paid model is used wherever the local one misses the targets. Railway cannot host a local model affordably, so the deployed pilot uses the paid adapter.
