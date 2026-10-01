# RankUno 1Stop — Risk Register

| | |
| :-- | :-- |
| **Document ID** | `RKN-1STOP-RISK-V1` |
| **Date** | 2026-09-30 (re-rated for internal-only scope and minimum spend) |
| **Owner** | AI Lead |

**Scale:** Likelihood and Impact are each rated L (low), M (medium) or H (high). Review this register at every weekly checkpoint; any risk rated H/H blocks Gate G2 until it has a tested mitigation.

| ID | Risk | L | I | Mitigation | Validated in | Status |
| :-- | :-- | :-: | :-: | :-- | :-- | :-- |
| R-01 | **Secrets in ingested content** (`.env`, keys, service-account JSON in repos or zips) reach the index, an LLM provider, logs or an answer. Evidence: F-03. | H | H | Secret scan (working tree + history) before any processing; quarantine; private owner notice with paths only; nothing quarantined is embedded or sent to an LLM. | S-03 | Open |
| R-02 | **Indirect prompt injection** via docs (including `CLAUDE.md`/agent files that contain instructions) makes the assistant recommend harmful commands or leak data. | M | H | Delimited untrusted context; commands only from owner-approved card fields or quoted verbatim with their source; no remote images; link allowlist; red-team suite in CI. | S-11 | Open |
| R-03 | **Restricted-doc leakage.** Docs mentioning client data or credential procedures are shown to all staff. *(Was: cross-tenant leakage; re-scoped 2026-09-30.)* | M | M | `restricted` flag set by owners; enforced in every retrieval query with tests; restricted content never sent to a training-enabled LLM tier. | P3, S-11 | Open |
| R-04 | **API abuse** through a host tool's public Railway URL drains the LLM budget. *(Likelihood lowered: internal tools.)* | L | M | Per-tool keys, origin allowlist, rate limits, persisted daily cap, kill switch. | S-10 | Open |
| R-05 | **Hallucinated capabilities.** The assistant says a tool does X when it doesn't. | M | H | Grounded-only answers with citations; `UNKNOWN` status; owner-approved cards; groundedness judge in CI; "report outdated" button. | S-07, P5.6 | Open |
| R-06 | **Low adoption.** Staff keep asking colleagues. | M | H | Put the assistant **inside the tools** people already use (in-tool channel); high catalog coverage before launch; pilot group; time-to-find vs baseline. | P1, R1 pilot | Open |
| R-07 | **Authors skip or rush the onboarding handover.** *(Re-scoped 2026-09-30: authors aren't needed after handover, so the risk concentrates in that one session.)* | M | M | Short structured handover (20–30 min); drafted card ready beforehand; non-author exit check (P4.8). | P1.2, P4.8 | Open |
| R-08 | **Stale knowledge.** Tools in development change weekly, and sync is weekly by decision (D-06), so answers can lag by up to a week. | H | M | Every answer shows the cited doc's date; docs older than the tool's last release are down-weighted; admin-only `sync now` after big changes; readiness rules; gap loop. | P4, P8 | Open (accepted trade-off) |
| R-09 | **Widget harms the host tool** (CSS bleed, CSP breakage, slowdown). | L | M | iframe isolation; < 50 KB async loader; lazy iframe; tested in RAE and prompt-engine first. | S-09 | Open |
| R-10 | **Malicious or pathological archives** in Drive. | L | H | Size/ratio/count/depth limits; path normalisation; no symlinks; sandboxed extraction; malware scan. | S-03 | Open |
| R-11 | **LLM cost overrun.** | L | M | Minimum-cost design (D-28): one call per question, caching, cheap model, persisted daily cap enforced by `CostLedger`. | P9.4, S-15 | Open |
| R-12 | **Personal data** in staff conversations handled without clear notice or retention. *(Lowered: staff only.)* | L | M | Tell staff what is logged; retention per D-23; logs redacted by default. | P9.5 | Open |
| R-13 | **Over-broad Drive access.** | L | M | Share only the registry folder with the service account, read-only. | S-01 | Open |
| R-14 | **Scope creep** (catalog + in-tool assistant + compliance + matrix at once). | M | M | Release 1 is deliberately small; the matrix and compliance digests come in R2; the widget is enabled one tool at a time. | Gate G1 | Open |
| R-15 | **Latency** from region hops. | M | L | Railway region nearest Supabase `ap-south-1`; status event first; measure in S-13. | S-13 | Open |
| R-16 | **Model/provider change** (deprecation, price, free-tier terms). | M | M | Provider abstraction; pinned model IDs; the eval suite gates any switch. | S-15 | Open |
| R-17 | **Suggestive tone suppresses necessary warnings.** | M | M | Explicit safety exemption; the judge checks warnings are retained. | S-08 | Open |
| R-18 | **Credential hygiene in organisation docs.** Shared plaintext password in the accounts record (F-20). | H | H | Rotate; password manager; exclude `project-standards/docs` from ingestion until clean. | P0.7 | Open. **Action outside this project.** |
| R-19 | **Data processing location.** Internal docs processed by LLM providers outside India. | M | L | Record each provider's region and retention; local embeddings mean only the answer call leaves RankUno infrastructure. | P9.5 | Open |
| R-20 | **Bus factor.** One person holds the design, approvals and credentials. | H | M | ADRs; runbooks; credentials in a password manager; a second maintainer identified by R2. | P11 | Open |
| R-21 | **Evaluation debt.** | M | H | Harness and golden sets in Phase 5 before features; the CI gate blocks regressions. | P5 | Open |
| R-22 | ~~Identity-platform assumption wrong~~ | — | — | **Closed 2026-09-30:** Entra ID later, Gmail for testing, registry in Drive. Replaced by R-26. | — | Closed |
| R-23 | **Building what a free tool already does.** | L | M | One-hour free/self-hosted alternatives check (D-02). | P2 | Open |
| R-24 | **Free LLM tiers may train on inputs.** Sending internal docs or code to such a tier leaks RankUno knowledge. *(New.)* | M | H | Only use tiers whose terms exclude training on inputs for real content; record the terms checked and the date in D-11; synthetic data only on training-enabled tiers. | S-15 | Open |
| R-25 | **Free-tier limits and behaviour.** Supabase free projects may pause after inactivity, and have storage/connection limits; the local embedding model may exceed Railway memory. *(New.)* | M | M | Check current free-tier terms; a lightweight daily job keeps the project active if needed; measure worker memory in S-06; the upgrade path is recorded in D-28. | S-06, P10 | Open |
| R-26 | **The test Gmail becomes a hidden production dependency** (Drive ownership, email sending, service accounts tied to a personal-style account). *(New.)* | M | M | Every Gmail-bound piece sits behind an interface (file source, email sender, auth); a migration checklist to Entra ID / Microsoft 365 is written before pilot rollout; credentials in a password manager, not one person's head. | P10, R1 | Open |
| R-27 | **Superseded or status-only docs outrank current ones** (old ADRs, "FIXES_REQUIRED" files), giving outdated answers. *(New, F-21.)* | H | M | Doc-type and supersession parsing; recency weighting; owner-declared authoritative paths (`1stop.yaml`); every answer shows its source's date. | P4, S-05 | Open |
| R-28 | **Tacit knowledge lost after handover.** Once the author is no longer needed, questions the docs don't cover have nobody to answer them, and maintenance of every stable tool falls on the admin. *(New, D-29.)* | M | H | Handover questionnaire captured as FAQs (P4.8); non-author exit check; answered gaps become FAQs so each question escalates at most once; developers stay maintainers while tools are still changing (Q-A06). | P4.8, R3 | Open |
