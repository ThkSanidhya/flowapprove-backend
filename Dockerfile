FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for mysqlclient
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/staticfiles

EXPOSE 8000

# Healthcheck hits the admin login page (cheap, no auth needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/admin/login/ || exit 1

# Entrypoint: run migrations then start gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn flowapprove_backend.wsgi:application --bind 0.0.0.0:8000 --workers 4 --access-logfile - --error-logfile -"]
