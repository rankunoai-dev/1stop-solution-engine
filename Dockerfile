# ── Stage 1: build the React SPA ─────────────────────────────────────────────
FROM node:20-slim AS web-builder
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --prefer-offline
COPY web/ .
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Create non-root user
RUN addgroup --system onestop && adduser --system --ingroup onestop onestop

WORKDIR /app

# Install Python deps first (better layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

# Copy application source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Copy built SPA from stage 1
COPY --from=web-builder /web/dist ./web/dist

# Non-root user
RUN chown -R onestop:onestop /app
USER onestop

EXPOSE 8000

CMD ["onestop", "serve", "--host", "0.0.0.0", "--port", "8000"]
