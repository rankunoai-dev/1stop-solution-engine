# RankUno 1Stop — Open Questions and Interview Guides

| | |
| :-- | :-- |
| **Document ID** | `RKN-1STOP-QUES-V1` |
| **Date** | 2026-09-30 (first answers recorded) |
| **Owner** | AI Lead |

## 1. How to use this

Questions are grouped by **who can answer them**, so each conversation covers its whole group. Record answers inline (`**Answer (date, source):** …`) and move any consequence into the decision log or risk register the same day.

**Prefixes:** L = leadership/owner · I = IT/accounts · U = tool seekers · O = tool owners (catalog) · T = in-house tools that will host the assistant · A = catalog admin · X = security/data. *(The Q-S "SaaS product" group was replaced by Q-T on 2026-09-30, when the embedded assistant was re-scoped to in-house tools.)*

## 2. Blocking questions: status

| ID | Question | Answer |
| :-- | :-- | :-- |
| **Q-I01** | Staff identity and file locations? | **Answered 2026-09-30 (owner):** Microsoft Entra ID will be the staff identity; testing runs on a Gmail account; the Excel registry stays in Google Drive. → F-04, D-20, D-21. |
| **Q-L01** | Who approves the gates? | **Answered 2026-09-30:** the AI Lead approves everything during testing. |
| **Q-L02** | Budget? | **Answered 2026-09-30:** minimum dollar spend. → D-28. **2026-10-01:** the owner wants costs kept low throughout initial development. *Still to confirm:* the numbers. Proposed: $1/day and $10/month LLM ceilings during development; spike budget ≤ $15. |
| **Q-L04** | Internal or SaaS first? | **Answered 2026-09-30:** internal first. → D-01. |
| **Q-T01** | Which in-house tools will host the assistant first? | **Partly answered:** several in-house tools in development. **Still needed:** names, repo URLs, owners, and which one pilots. |

**Next to answer (now blocking Phase 2):**

| ID | Question | Why it matters |
| :-- | :-- | :-- |
| **Q-T01** | The list of in-house tools that will embed the assistant, with repo links and owners. Is RAE one? prompt-engine? | Pilot choice, golden set, S-09 |
| **Q-A02** | Share (read-only) the Drive folder containing the Excel registry with the test account; is it `.xlsx` or a Google Sheet? | S-01, S-02. **Owner will provide (2026-09-30);** S-02 records rows, columns and completeness from the file itself. |
| **Q-I05** | Can a read-only GitHub token be created for the `rankunoai-dev` repos to be indexed? | S-03, S-04 |
| **Q-L07** | Confirm the LLM daily cap and which paid LLM account (if any) may be used for real internal docs. | D-11, D-28, R-24 |

## 3. Tool seekers: interview guide (Q-U), 30 minutes

*Opening:* "We're looking at how people find and use tools other RankUno people have built. There are no right answers; we want the real story."

- **Q-U01** Tell me about the last time you needed a script or tool for a task. What was the task? What did you do first?
- **Q-U02** Did you find something existing? How? How long did it take? If not, did you build it? How long did that take?
- **Q-U03** If you could type your problem into a box, what exactly would you type? *(Collect 5 verbatim problem statements; they go into the golden set.)*
- **Q-U04** Where do you spend your working day: browser, Teams, IDE, a particular in-house tool? Where would you most naturally ask?
- **Q-U05** What makes you trust a tool someone else built? What makes you avoid it?
- **Q-U06** When a tool nearly fits, do you adapt it or start fresh? Why?
- **Q-U07** Would a side-by-side comparison of several candidate tools help, or would you just want the best one?
- **Q-U08** How do you feel about an assistant that suggests rather than instructs?
- **Q-U09** When you get stuck *inside* one of our tools, what do you do? Who do you ask? *(Collect 5 verbatim "how do I…" questions per tool; they become the in-tool golden set.)*
- **Task test:** 3 problems with known answers; time the current method (the baseline for "time to find").

## 4. Tool owners: interview guide (Q-O), 30 minutes

- **Q-O01** Walk me through your tool. In one paragraph, what problem does it solve and for whom? *(Ground truth for spike S-04.)*
- **Q-O02** Where does the code live? Is that the only copy? Is it deployed anywhere?
- **Q-O03** Does the repo or its history contain credentials, client data, or anything that must not be shared internally?
- **Q-O04** How often do colleagues ask you about it? What do they ask? Would you rather they asked a bot first?
- **Q-O05** If 1Stop auto-drafted a catalog card from your repo, would you spend 15 minutes reviewing it? What would stop you?
- **Q-O06** How would you like to be reminded about missing documentation: email digest, Teams, in-app, never? How often is too often?
- **Q-O07** Which files in your repo are the **current, authoritative** docs, and which are old notes? Would you list them in a small `1stop.yaml`?
- **Q-O08** What would make you proud of your tool's catalog entry?
- **Q-O09** Which of your tools are dead or superseded?

## 5. Catalog admin (Q-A)

- **Q-A01** Who maintains the Excel registry today, and how often is it updated?
- **Q-A02** Share it read-only for spike S-02. `.xlsx` or Google Sheet? How many rows, which columns, how complete? *(See §2.)*
  **Answer (2026-09-30, owner):** Access will be provided. S-02 measures rows, columns and completeness directly from the file instead of relying on a description.
- **Q-A03** Which compliance rules matter most? Which are nice-to-have?
- **Q-A04** What happens to a tool when its owner leaves RankUno?
  **Answer (2026-09-30, owner):** Once a tool is onboarded, its original owner is no longer needed. The design therefore splits **author** (needed only for the onboarding handover) from **maintainer** (receives unanswered questions and doc reminders; defaults to the platform admin after handover). The handover must capture the author's tacit knowledge so the knowledge base stands on its own (D-29, P4.8, R-28).
- **Q-A06** For tools still in active development: is the developer currently changing the code the maintainer until the tool is stable? *(Proposed: yes; the maintainer switches to the admin only when the tool is marked stable.)*
- **Q-A05** Are there tools or docs that must be visible only to certain people (the `restricted` flag)?

## 6. In-house tools that will host the assistant (Q-T), 30 minutes per tool

- **Q-T01** Tool name, repo, owner, status (in development / live), URL. *(See §2.)*
- **Q-T02** Stack: frontend framework, backend, where it's hosted, whether it has its own login.
- **Q-T03** Who uses it: only RankUno staff, or also clients? *(Tests assumption A-13; client users would change the privacy and security scope.)*
- **Q-T04** Where are its docs (README, `docs/`, ADRs, `CLAUDE.md`, API spec)? Which are current?
- **Q-T05** What do users get stuck on most? Top 5–10 questions.
- **Q-T06** Which screens or features would benefit from context-aware help (e.g. config forms, error states)?
- **Q-T07** Can the tool pass the logged-in user's email to the widget (for the pilot stage of D-17)?
- **Q-T08** What must the assistant never say or do for this tool?
- **Q-T09** Should the assistant be able to link to specific pages in the tool? Can the owner provide a route list?
- **Q-T10** How often does the tool change? Is there a release/changelog we can use for freshness?

## 7. Leadership and owner (Q-L)

- **Q-L01** Approver. *(Answered, §2.)*
- **Q-L02** Budget. *(Answered: minimum spend, §2.)*
- **Q-L03** How much of the AI Lead's time is allocated over the next 6 weeks?
- **Q-L04** Priority. *(Answered: internal first.)*
- **Q-L05** Is a free, self-hosted existing tool acceptable if it covers a big part of the need? (D-02)
- **Q-L06** Could any in-house tool become a product for RankUno clients? *(If yes, the external-space path in D-03 becomes relevant.)*
- **Q-L07** LLM daily cap and permitted paid LLM account. *(See §2.)*

## 8. IT and accounts (Q-I)

- **Q-I01** Identity. *(Answered, §2.)*
- **Q-I02** Can the registry folder be shared read-only with a Google Cloud service account?
- **Q-I03** Before rollout: who can register an app in Microsoft Entra ID for "Sign in with Microsoft"?
- **Q-I04** Before rollout: which Microsoft 365 mailbox should send 1Stop emails?
- **Q-I05** Read-only GitHub token for selected `rankunoai-dev` repos. *(See §2.)*
- **Q-I06** Has the shared credential in the infrastructure accounts record been rotated? *(Risk R-18.)*

## 9. Security and data (Q-X)

- **Q-X01** Do any tool docs contain client data that client contracts forbid sending to AI providers?
- **Q-X02** Is processing of internal docs by LLM providers outside India acceptable? *(Local embeddings already keep indexing inside RankUno infrastructure.)*
- **Q-X03** How long should staff conversations be kept? (D-23 proposes 180 days.)
