# Deploying 1Stop to Railway

This guide walks through deploying the 1Stop application to Railway using the multi-stage
`Dockerfile`. The deployment runs `alembic upgrade head` before starting the server, so the
database schema is always in sync on each deploy.

---

## 1. Prerequisites

- A **Railway** account at [railway.app](https://railway.app)
- A **Supabase** project at [supabase.com](https://supabase.com) (free tier is sufficient for
  the pilot)
- A **Gmail** account with an **App Password** created
  (Google Account → Security → 2-Step Verification → App Passwords)
- The `1stop-solution` repository pushed to GitHub

---

## 2. Supabase setup

1. Create a new Supabase project and note your project reference ID.
2. In **Project Settings → Database**, find the **Connection string** (URI format). Use the
   **Session mode** pooler URL (port 5432), not the transaction mode pooler.
3. Prefix the driver: replace `postgresql://` with `postgresql+psycopg://`.
   The final string looks like:
   ```
   postgresql+psycopg://postgres.xxxx:[password]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
   ```
4. Set `search_path=onestop` by appending `?options=-c%20search_path%3Donestop` to the URL,
   or set it on the Supabase database role. The migration creates the `onestop` schema on first
   run.

---

## 3. Railway setup

1. Go to [railway.app](https://railway.app) and create a **New Project**.
2. Choose **Deploy from GitHub repo** and select the `1stop-solution` repository.
3. Railway detects `railway.json` and uses the `Dockerfile` automatically.
4. Set the environment variables listed in section 4 below via
   **Project → Variables**.
5. Click **Deploy**. Railway will:
   - Build the multi-stage Docker image (Node 20 → React SPA → Python 3.11)
   - Run `alembic upgrade head` to create or migrate the database schema
   - Start `onestop serve` on the port Railway assigns

Each subsequent push to the tracked branch triggers an automatic redeploy.

---

## 4. Required environment variables

Set all of these in Railway's **Variables** panel. Variables marked **secret** should never be
committed to the repository.

| Variable | Description | Example / How to get it |
| :-- | :-- | :-- |
| `ENVIRONMENT` | Deployment mode | `production` |
| `DATABASE_URL` | Supabase connection string | `postgresql+psycopg://postgres.xxxx:[pw]@...` |
| `SESSION_SECRET` | Random 64-char hex string for session signing **(secret)** | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `BOOTSTRAP_ADMIN_EMAIL` | Email of the first admin user, created on startup | `manoj.dhote@rankuno.com` |
| `ALLOWED_EMAILS` | Comma-separated list of staff emails allowed to log in | `alice@rankuno.com,bob@rankuno.com` |
| `SMTP_HOST` | Gmail SMTP host | `smtp.gmail.com` |
| `SMTP_PORT` | Gmail SMTP port | `587` |
| `SMTP_USER` | Gmail address used to send login codes | `noreply@rankuno.com` |
| `SMTP_PASSWORD` | Gmail App Password **(secret)** | 16-character code from Google Account settings |
| `SMTP_FROM` | From address shown in login-code emails | `noreply@rankuno.com` |
| `LLM_PROVIDER` | Which LLM backend to use | `ollama` (free, local) or `anthropic` / `gemini` for the pilot |
| `LLM_MODEL` | Model name for the configured provider | `llama3.2` for Ollama; `claude-haiku-4-5` for Anthropic |
| `OLLAMA_BASE_URL` | URL of the Ollama server (only when `LLM_PROVIDER=ollama`) | `http://your-ollama-host:11434` |
| `ANTHROPIC_API_KEY` | Anthropic API key (only when `LLM_PROVIDER=anthropic`) **(secret)** | From console.anthropic.com |
| `GEMINI_API_KEY` | Google Gemini API key (only when `LLM_PROVIDER=gemini`) **(secret)** | From aistudio.google.com |
| `SPEND_CAP_DAY_USD` | Daily LLM spend limit in USD | `1.00` |
| `SPEND_CAP_MONTH_USD` | Monthly LLM spend limit in USD | `10.00` |
| `APP_URL` | The Railway-assigned public URL (used for CORS) | `https://onestop-production.up.railway.app` |
| `SENTRY_DSN` | Sentry error tracking DSN (optional) **(secret)** | From your Sentry project settings |

> **SESSION_SECRET generation:**
> ```
> python -c "import secrets; print(secrets.token_hex(32))"
> ```
> Run this locally and paste the output. Never reuse the development value.

> **ALLOWED_EMAILS note:** Leave blank to allow any email. Set it to a comma-separated list of
> staff emails to restrict access. The bootstrap admin is automatically allowed regardless.

---

## 5. Verify the deployment

Once the deploy is green in Railway's dashboard:

1. **Health check** — Railway calls `GET /health` automatically. You can also check it:
   ```
   curl https://your-app.up.railway.app/health
   # Expected: {"status":"ok"}
   ```

2. **Login** — open `https://your-app.up.railway.app` in a browser. You should see the 1Stop
   login page. Enter the `BOOTSTRAP_ADMIN_EMAIL` address and click "Send code". A 6-digit
   login code arrives by email.

3. **Test chat** — after logging in, send a test message in the Chat page.
   - If `LLM_PROVIDER=ollama` and no Ollama server is reachable, the response will be an error.
     That is expected until the Ollama server is configured (R1 adds hosted-provider support).
   - If `LLM_PROVIDER=anthropic` or `gemini` and the API key is set, you should receive a real
     LLM response.

4. **Admin panel** — navigate to `/admin`. You should see the Users, Spend, and Jobs tabs.

---

## 6. Rollback

Railway keeps the previous deployment. To roll back:

1. Open the Railway project dashboard.
2. Click **Deployments** in the left sidebar.
3. Find the previous successful deployment and click **Rollback**.

The database schema is not rolled back automatically. If a migration must be reversed, run
`alembic downgrade -1` manually via a Railway one-off process or a local connection.

---

## 7. Local Docker test

Before pushing to Railway, you can test the image locally:

```powershell
# Build the image
docker build -t onestop .

# Run with your local .env
docker run -p 8000:8000 --env-file .env onestop

# Open in browser
# http://localhost:8000/health  →  {"status":"ok"}
# http://localhost:8000/        →  Login page (SPA)
```

> **Note:** `docker build` requires Docker Desktop to be running. The `.dockerignore` excludes
> `.env` from the image; `--env-file .env` injects it at runtime only.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
| :-- | :-- | :-- |
| Build fails with `npm not found` | Docker not using the correct stage | Confirm `Dockerfile` is in the repo root |
| `ConfigurationError: Production configuration is incomplete` | Missing required env vars | Check Railway Variables against section 4 |
| `GET /health` returns 502 | Server hasn't started yet, or crash | Check Railway logs; `alembic upgrade head` may have failed |
| Login code email not received | SMTP credentials wrong or Gmail App Password expired | Verify `SMTP_PASSWORD` in Gmail Account settings |
| Chat returns `cap_reached` error | Daily or monthly spend cap hit | Raise `SPEND_CAP_DAY_USD` / `SPEND_CAP_MONTH_USD`, or use the kill switch toggle in the Admin → Spend page |
