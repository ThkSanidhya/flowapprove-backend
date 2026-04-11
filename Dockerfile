FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: curl for the healthcheck + libpq for psycopg2-binary (binary
# wheel bundles libpq, but libpq5 must be present at runtime on slim images).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles && chmod +x docker-entrypoint.sh

EXPOSE 8000

# Healthcheck hits the dedicated liveness probe (cheap, no auth needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Entrypoint: wait-for-postgres -> migrate -> collectstatic -> gunicorn
CMD ["./docker-entrypoint.sh"]
