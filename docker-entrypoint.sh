#!/bin/sh
# Docker entrypoint for the FlowApprove backend.
#
# Render's free Postgres can be reported "available" a few seconds before
# the server actually accepts TCP connections, and the web service often
# boots first on a fresh Blueprint deploy. This script blocks on the DB
# being reachable before running migrate, then starts gunicorn.

set -e

python <<'PYEOF'
import os
import sys
import time
import urllib.parse

import psycopg2

# Parse DATABASE_URL if present, else fall back to individual DB_* vars.
url = os.environ.get("DATABASE_URL")
if url:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 5432
    user = parsed.username
    password = parsed.password
    dbname = (parsed.path or "/").lstrip("/") or "postgres"
else:
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    dbname = os.environ.get("DB_NAME", "postgres")

deadline = time.time() + 120  # 2 minutes
attempt = 0
while True:
    attempt += 1
    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname=dbname,
            connect_timeout=5,
        )
        conn.close()
        print(f"[entrypoint] Postgres reachable on attempt {attempt}", flush=True)
        break
    except psycopg2.OperationalError as exc:
        if time.time() > deadline:
            print(f"[entrypoint] Postgres still unreachable after {attempt} attempts: {exc}", flush=True)
            sys.exit(1)
        print(f"[entrypoint] Waiting for Postgres ({attempt})... {exc}", flush=True)
        time.sleep(2)
PYEOF

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput || echo "[entrypoint] collectstatic failed, continuing"

echo "[entrypoint] Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn flowapprove_backend.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 4 \
    --access-logfile - \
    --error-logfile -
