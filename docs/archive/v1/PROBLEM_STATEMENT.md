# RankUno 1Stop Solution — Problem Statement Document

**Document Version:** 1.0.0  
**Target Platform:** RankUno 1Stop Solution (Intelligent Utility Discovery & Assistant Platform)  
**Author:** AI Systems Architecture Team  
**Date:** September 2026  

---

## 1. Executive Summary

At RankUno, engineers and technical staff across teams frequently develop specialized internal utility tools—ranging from data transformation scripts, API migration wrappers, batch file processors, to custom report generators. While these tools solve immediate project challenges, they operate in silos. 

As a result, company-wide utility discovery is fragmented, leading to duplicate software development efforts, wasted engineering hours, low visibility of high-value internal tools, and operational friction. **RankUno 1Stop Solution** is designed to address this problem by creating an intelligent, AI-powered utility discovery platform that scans, ingests, categorizes, matches, and guides employees toward existing internal solutions using an always-suggestive, non-prescriptive AI assistant.

---

## 2. Current State & Pain Points

### 2.1 Fragmented Tool Landscape & Redundancy
* **Unstructured Repositories & Drive Folders:** Internal tools are scattered across personal Google Drive folders, local workstations, and isolated repositories.
* **Re-inventing the Wheel:** Developers frequently build custom scripts for problems that have already been solved by peers in another department or project team.
* **Zero Discoverability:** Keyword-based file searches in Google Drive fail when an engineer’s problem description uses different terminology than the original tool's title or brief description.

### 2.2 Lack of Standardized Documentation & Quality Control
* **Incomplete Uploads:** Utilities uploaded to central storage often lack setup guides, API specifications, dependency declarations, or problem context.
* **Decay of Metadata:** As tools evolve, their catalog entries (if any) become obsolete, rendering them unusable by team members without direct author intervention.
* **No Compliance Enforcement:** Administrators currently have no automated mechanism to check whether uploaded tools contain compulsory documentation, architecture notes, or registry details.

### 2.3 Suboptimal Discovery User Experience
* **Inelastic Search Interfaces:** Conventional search engines cannot break down complex, multi-faceted engineering problems into discrete requirements to evaluate partial tool matches.
* **Rigid & Prescriptive Bot Persona:** Existing chatbots or recommendation systems often issue authoritative directives ("*You must use X*", "*You should execute Y*"), creating friction and reducing engineer autonomy.
* **Single-Tool Bias:** Traditional recommendation tools return a single "best match," ignoring scenarios where multiple tools satisfy different subsets of a user's requirements.

---

## 3. Core Objectives & Vision

**1Stop Solution** aims to transform internal asset discovery into a seamless, intelligent pair-engineering experience through five core pillars:

```
+-----------------------------------------------------------------------------------+
|                                 1Stop Solution                                    |
+-----------------------------------------------------------------------------------+
|  1. Problem Decomposition Engine  --> Atomic Criteria Extraction (C1, C2, C3...)    |
|  2. Multi-Utility Matching        --> Side-by-Side Comparative Matrix & UI         |
|  3. Suggestive Tone Engine        --> Non-Directive, Empowering Guidance Persona  |
|  4. Weekly Drive & Excel Resync   --> Automated Compliance & Zip Inspection       |
|  5. AI Intelligence Extraction    --> 5-Phase Enriched Knowledge Base Indexing    |
+-----------------------------------------------------------------------------------+
```

1. **Intelligent Problem Decomposition:** Automatically parse a user's natural language problem statement into atomic criteria ($C_1, C_2, \dots, C_n$), categorized by Functionality, Tech Stack, Input/Output formats, Deployment requirements, and Priority levels.
2. **Multi-Utility Comparative Discovery:** When multiple tools match a user's problem, present all relevant tools side-by-side with color-coded criterion-level status badges (✅ Fully Met, 🟡 Partially Met, ❌ Not Met, 🔧 Adaptable) and percentage match scores.
3. **Always-Suggestive AI Persona:** Enforce a non-directive communication protocol where the AI assistant acts as a helpful colleague offering options ("*DataTransformer could be a great fit for...*") rather than issuing commands.
4. **Automated Master Sync & Compliance Scanner:** Implement a scheduled (weekly) batch process that scans an **Excel Master Registry** in Google Drive and validates each utility's **Zip file contents** against admin-configurable rules (README, Installation Guide, Problem Statement).
5. **Automated Compliance Alerting:** Automatically dispatch polite, suggestive email notifications to tool owners when required documents or fields are missing, encouraging compliance without punitive friction.

---

## 4. Target Audience & System Boundaries

* **Target Users:** ~50 initial internal engineers, analysts, and project managers at RankUno (scalable up to enterprise levels).
* **Catalog Scale:** Initial catalog of $\le 100$ internal utilities, growing over time.
* **Deployment Model:** Single-server containerized stack via Docker Compose, leveraging local PostgreSQL, Qdrant vector database, and Redis cache.
* **Language Support:** English primary language communication for queries, documentation, and notifications.

---

## 5. Success Criteria & KPIs

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| **Search-to-Discovery Time** | $< 30$ seconds | Analytics tracking from prompt submission to tool walkthrough view |
| **Redundant Code Reduction** | $> 40\%$ decrease | Semi-annual engineering audit of internal script creation |
| **Tool Documentation Compliance** | $> 90\%$ compliant zip/registry entries | Automated compliance scanner audit metrics |
| **System Latency (First Stream Token)** | $< 500$ ms | Server-Sent Events (SSE) stream initiation timer |
| **User Satisfaction (CSAT)** | $> 4.5 / 5.0$ | Post-interaction rating on suggestive response usefulness |

---

## 6. Document Roadmap

* **`INVESTIGATION_REPORT.md`**: Comprehensive technical investigation, detailed architectural flowcharts, database schemas, algorithm formulations, and component designs.
* **`README.md`**: Complete repository guide, installation walkthrough, configuration specs, admin settings overview, and API specifications.
