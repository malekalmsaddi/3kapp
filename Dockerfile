# syntax=docker/dockerfile:1

# ── Build stage: compile wheels that need gcc / libpq-dev ──────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ── Runtime stage: only runtime libs, no build toolchain ──────────────────
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl procps postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY . .

# Non-root user setup
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8080

CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-8080} app:app --workers 1 --threads 2"]
