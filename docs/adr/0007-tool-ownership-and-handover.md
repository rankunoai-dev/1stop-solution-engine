# ADR 0007 — Tool ownership: author handover, then maintainer

**Status**: Accepted (owner, 2026-09-30) · **Decision log**: D-29 · **Risks**: R-07, R-28

## Context
The owner decided that once a tool is onboarded, its original creator is no longer needed.

## Decision
- `tools.author_*` records who built it (history). `tools.maintainer_email` routes unanswered questions and reminders; it defaults to the admin once `is_stable` is true. A developer still changing the tool stays maintainer.
- Onboarding = card review + handover questionnaire (top questions, gotchas, error fixes, never-do list, stability). Answers are stored in `handover_answers` and indexed as `faq` documents.
- Exit check: a non-author answers 8 of 10 golden questions for the tool using only 1Stop.

## Consequences
The knowledge base must stand alone after handover; the admin carries maintenance of stable tools, kept small by turning every answered gap into an FAQ.
