# 🚀 RankUno 1Stop Solution — Intelligent Utility Discovery & Assistant Platform

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-15.0-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688?logo=fastapi)
![Qdrant](https://img.shields.io/badge/Qdrant-VectorDB-red?logo=qdrant)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16.0-4169E1?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

**RankUno 1Stop Solution** is an AI-powered utility discovery platform and collaborative pair-engineering assistant. It enables engineers and technical teams at RankUno to describe their technical challenges in natural language, discover matching internal utilities, perform side-by-side comparative analysis, and receive suggestive, non-prescriptive guidance on tool adaptation.

---

## 🌟 Key Features

### 🧩 1. Problem Decomposition Engine
* Automatically breaks down natural language problem statements into **Atomic Criteria pills** ($C_1, C_2, C_3\dots$).
* Categorizes requirements by category (`FUNCTIONAL`, `INPUT_FORMAT`, `TECH_STACK`, `INTEGRATION`, etc.) and priority (`MUST_HAVE`, `NICE_TO_HAVE`, `FLEXIBLE`).

### 📊 2. Multi-Utility Matching & Side-by-Side Comparison UI
* Evaluates multiple candidate internal utilities criterion-by-criterion.
* Displays a side-by-side comparison matrix with status badges:
  * ✅ **Fully Met** — Requirement satisfied out-of-the-box.
  * 🟡 **Partially Met** — Satisfied with minor configuration adjustments.
  * ❌ **Not Met** — Feature not supported by the utility.
  * 🔧 **Adaptable** — Feature can be extended via custom wrapper/plugin.
* Computes weighted match percentage scores and highlights utility strengths.

### 💬 3. Always-Suggestive AI Tone Directive
* Enforces a collaborative, non-directive tone across all responses.
* The assistant uses suggestive phrases (*"DataTransformer could be a great fit"*, *"You might consider extending the validator"*) and avoids commanding statements (*"You must use X"*).

### 🔄 4. Weekly Resync & Excel Master Registry Scanner
* Scheduled weekly batch process (via Celery Beat cron) scanning a central **Excel Master Registry** in Google Drive.
* Inspects uploaded **Zip file structures** against admin-configured mandatory rules (e.g., `README.md`, `PROBLEM_STATEMENT.md`, `INSTALL.md`).

### 📧 5. Automated Compliance Email Alerts
* Sends polite, suggestive email notifications to utility owners when required documentation or Excel metadata is missing, encouraging documentation compliance.

### 🧠 6. 5-Phase AI Intelligence Extraction Pipeline
* Runs 5 structured LLM scans on compliant utilities during sync:
  1. **Problem Context Extraction**
  2. **Capability Mapping**
  3. **Tech Stack Fingerprinting**
  4. **Integration Point Discovery**
  5. **Adaptability & Modification Assessment**
* Stores rich intelligence facets in **Qdrant Vector DB** and **PostgreSQL**.

---

## 📐 System Architecture

```
+-------------------------------------------------------------------------+
|                        Next.js 15 App Router Frontend                   |
|       (Chat Interface, Comparison Matrix UI, Admin Settings Panel)      |
+-------------------------------------------------------------------------+
                                    | (Server-Sent Events / REST API)
                                    v
+-------------------------------------------------------------------------+
|                          FastAPI Backend Service                        |
|  - 3-Tier Intent Router         - Problem Decomposition Engine          |
|  - Multi-Utility Matcher        - Always-Suggestive Tone Directive      |
|  - Celery Batch Resync          - 5-Phase Intelligence Extraction       |
+-------------------------------------------------------------------------+
           |                        |                       |
           v                        v                       v
+--------------------+    +--------------------+    +---------------------+
| Qdrant Vector DB   |    | PostgreSQL DB      |    | Redis Cache Store   |
| (Dense + Sparse)   |    | (Metadata/Logs)    |    | (Sessions & Buffer) |
+--------------------+    +--------------------+    +---------------------+
```

---

## 📁 Repository Structure

```text
1stop-solution/
├── PROBLEM_STATEMENT.md         # Core business problem statement & objectives
├── INVESTIGATION_REPORT.md      # Detailed technical architecture & specs
├── README.md                    # Project README & setup guide
├── docker-compose.yml           # Multi-container orchestration specification
├── .env.example                 # Environment variables template
│
├── frontend/                    # Next.js 15 App Router Frontend
│   ├── src/
│   │   ├── app/                 # App Router pages (chat, comparison, settings)
│   │   ├── components/          # UI Components (cards, matrix, pills, badges)
│   │   ├── hooks/               # Custom React hooks (useChatSSE, useComparison)
│   │   ├── lib/                 # Utility functions & API clients
│   │   └── types/               # TypeScript type definitions
│   ├── public/                  # Static assets & icons
│   ├── package.json
│   └── tailwind.config.ts
│
├── backend/                     # FastAPI Backend Application
│   ├── app/
│   │   ├── api/                 # Endpoint handlers (chat, utilities, sync, admin)
│   │   ├── core/                # Core business logic
│   │   │   ├── router.py        # 3-Tier Intent Routing Engine
│   │   │   ├── decomposition.py # Problem Decomposition Engine
│   │   │   ├── matcher.py       # Multi-Utility Matcher & RRF Reranker
│   │   │   ├── tone_engine.py   # Suggestive Tone Enforcer
│   │   │   ├── sync_service.py  # Weekly Drive & Excel Resync Engine
│   │   │   └── intelligence.py  # 5-Phase Intelligence Extraction Pipeline
│   │   ├── models/              # Pydantic & SQLAlchemy Models
│   │   ├── db/                  # Qdrant & PostgreSQL client connections
│   │   └── config/              # Application settings & environment vars
│   ├── tests/                   # Backend pytest suite
│   ├── requirements.txt
│   └── main.py                  # FastAPI application entry point
│
└── scripts/                     # DevOps & Seed scripts
    ├── seed_data.py             # Database seeder with sample utilities
    └── run_resync.py            # Manual resync runner CLI
```

---

## 🛠️ Quick Start & Setup Guide

### Prerequisites
* **Docker** (v24.0+) & **Docker Compose** (v2.20+)
* **Python** (v3.11+) *(for local non-docker backend development)*
* **Node.js** (v20+) *(for local non-docker frontend development)*
* **Google Cloud Service Account** with Google Drive API access *(for Drive sync)*

---

### Step 1: Clone Repository & Configure Environment

```bash
git clone https://github.com/RankUno/1stop-solution.git
cd 1stop-solution

# Copy environment variables template
cp .env.example .env
```

Edit the `.env` file to add your API keys:
```env
# LLM Provider Configuration
LLM_PROVIDER=OPENAI                      # Options: OPENAI, CLAUDE, GEMINI
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_claude_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Database Configurations
POSTGRES_USER=rankuno
POSTGRES_PASSWORD=rankuno_secret
POSTGRES_DB=onestop_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

QDRANT_HOST=qdrant
QDRANT_PORT=6333

REDIS_HOST=redis
REDIS_PORT=6379

# Google Drive Sync Configuration
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id_here
EXCEL_REGISTRY_FILENAME=Utilities_Master.xlsx
SMTP_EMAIL_HOST=smtp.gmail.com
SMTP_EMAIL_PORT=587
SMTP_EMAIL_USER=notifications@rankuno.com
SMTP_EMAIL_PASSWORD=your_email_password
```

---

### Step 2: Launch via Docker Compose

```bash
docker-compose up -d --build
```

Verify that all services are running:
* **Frontend Chat Interface:** `http://localhost:3000`
* **FastAPI Swagger Docs:** `http://localhost:8000/docs`
* **Qdrant Dashboard:** `http://localhost:6333/dashboard`

---

### Step 3: Seed Sample Data (Optional)

To test the system with pre-loaded RankUno utility tools:

```bash
docker-compose exec backend python scripts/seed_data.py
```

---

## ⚙️ Admin Settings & Compliance Management

Admins can configure compliance rules directly via the UI settings panel (`http://localhost:3000/admin`):

1. **Excel Registry Required Columns:** Toggle mandatory fields (`Utility Name`, `Owner Email`, `Problem Statement`, `Tech Stack`, `Zip Link`).
2. **Zip Archive Rules:** Set mandatory files (`README.md`, `PROBLEM_STATEMENT.md`, `INSTALL.md`) and conditional rules.
3. **Weekly Resync Schedule:** Set cron frequency (default: Every Sunday at 00:00 UTC) or trigger an immediate manual resync.
4. **Email Alert Frequency:** Configure grace periods and alert thresholds for compliance notifications.

---

## 📖 API Documentation & Core Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/chat/stream` | Primary chat endpoint (SSE stream with criteria pills & matrix payload) |
| `POST` | `/api/v1/utilities/decompose` | Decompose a problem statement into atomic criteria pills |
| `POST` | `/api/v1/utilities/compare` | Evaluate candidate utilities against criteria matrix |
| `POST` | `/api/v1/sync/trigger` | Trigger manual resync & compliance scanner |
| `GET`  | `/api/v1/admin/compliance-report` | Fetch compliance status for all cataloged utilities |

---

## 📄 License & Attribution

Internal Proprietary Software — **RankUno Technology Solutions**.  
All rights reserved. Unauthorized copying or redistribution is strictly prohibited.
