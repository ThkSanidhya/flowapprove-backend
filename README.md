# FlowApprove Backend

Django + DRF API for **FlowApprove**, a multi-tenant document approval workflow system.

Sibling repos: [flowapprove-frontend](https://github.com/ThkSanidhya/flowapprove-frontend) · [flowapprove-docs](https://github.com/ThkSanidhya/flowapprove-docs)

The easiest way to run the full stack is from the [**meta-repo**](https://github.com/ThkSanidhya/flowapprove) with Docker. Keep reading if you want to run the backend natively.

**Database**: PostgreSQL 16. (Earlier versions used MySQL; the current code is Postgres-only — `psycopg2-binary` wheels mean no C++ build tools are needed on Windows.)

---

## Quickstart — Docker

From the parent directory (with sibling `flowapprove-frontend/` cloned):

```bash
docker compose up --build
```

This starts Postgres 16 + the backend (gunicorn) + the frontend (nginx). See the top-level meta-repo README for details.

---

## Quickstart — native (Linux / macOS)

### Prerequisites

- **Python 3.12+**
- **PostgreSQL 14+** running locally (or reachable via env vars)

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/ThkSanidhya/flowapprove-backend.git
cd flowapprove-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create a Postgres database

```bash
sudo -u postgres createuser --pwprompt flowapprove    # set a password
sudo -u postgres createdb -O flowapprove flowapprove
```

(macOS Homebrew Postgres: skip `sudo -u postgres` — run `createuser --pwprompt flowapprove` and `createdb -O flowapprove flowapprove` directly.)

### 3. Set environment variables

```bash
cp .env.example .env
# edit .env — at minimum set DB_PASSWORD and DJANGO_SECRET_KEY
export $(grep -v '^#' .env | xargs)
```

### 4. Migrate and run

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver    # http://127.0.0.1:8000
```

---

## Quickstart — native (Windows)

> **Seriously, just use Docker Desktop on Windows.** The native setup works but Docker is one command: `docker compose up --build`.

### Prerequisites

- **Python 3.12+** from <https://www.python.org/downloads/> (tick **"Add python.exe to PATH"** during install)
- **PostgreSQL 16** from <https://www.postgresql.org/download/windows/> (the EDB installer). Remember the `postgres` superuser password you set.
- **Git for Windows** from <https://git-scm.com/download/win>

No C++ Build Tools required — `psycopg2-binary` ships pre-compiled wheels for Windows.

### 1. Clone and create a virtualenv (PowerShell)

```powershell
git clone https://github.com/ThkSanidhya/flowapprove-backend.git
cd flowapprove-backend
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 2. Create a Postgres database

Open **pgAdmin** (installed with Postgres), or run `psql -U postgres` from the Start menu search:

```sql
CREATE USER flowapprove WITH PASSWORD 'your-password';
CREATE DATABASE flowapprove OWNER flowapprove;
```

### 3. Set environment variables (PowerShell)

```powershell
$env:DJANGO_SECRET_KEY = "dev-only-secret"
$env:DJANGO_DEBUG      = "True"
$env:DB_NAME           = "flowapprove"
$env:DB_USER           = "flowapprove"
$env:DB_PASSWORD       = "your-password"
$env:DB_HOST           = "127.0.0.1"
$env:DB_PORT           = "5432"
```

Command Prompt uses `set DB_PASSWORD=your-password` instead. To persist across sessions, set them via **System Properties → Environment Variables**.

### 4. Migrate and run

```powershell
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

The API is now available at **http://127.0.0.1:8000/**.

---

## Useful endpoints

| URL                                  | Purpose                                   |
|--------------------------------------|-------------------------------------------|
| `http://localhost:8000/api/docs/`    | Swagger UI — interactive API explorer     |
| `http://localhost:8000/api/redoc/`   | Redoc reference documentation             |
| `http://localhost:8000/api/schema/`  | Raw OpenAPI 3 YAML                        |
| `http://localhost:8000/healthz`      | Liveness + DB probe (no auth)             |
| `http://localhost:8000/admin/`       | Django admin (superuser account)          |

---

## Commands cheat sheet

| Task                      | Command |
|---------------------------|---------|
| Apply migrations          | `python manage.py migrate` |
| Create a migration        | `python manage.py makemigrations api` |
| Dev server                | `python manage.py runserver` |
| Run tests (SQLite, no Postgres needed) | `python manage.py test api --settings=flowapprove_backend.settings_test` |
| Run a single test         | `python manage.py test api.tests.RecallDocumentTests.test_creator_can_recall_pending_document --settings=flowapprove_backend.settings_test` |
| Create an admin           | `python manage.py createsuperuser` |
| Django system check       | `python manage.py check --deploy` |
| Generate OpenAPI schema   | `python manage.py spectacular --file schema.yml` |

On Windows, substitute `python` with `py` if that's how Python is installed.

---

## Architecture (short version)

- Single Django app `api/` holds everything.
- Function-based DRF views in `api/views.py`; business logic inline.
- Custom user model (`USERNAME_FIELD='email'`) with `role` (ADMIN/USER) and an `Organization` FK.
- **Multi-tenant**: every query is scoped by `request.user.organization`. Golden rules live in `CLAUDE.md`.
- 31 regression tests in `api/tests.py` cover multi-tenant isolation, approval state machine, version upload, recall, and configurable sendback.

Deeper dive: [flowapprove-docs/docs/architecture.md](https://github.com/ThkSanidhya/flowapprove-docs/blob/main/docs/architecture.md).

---

## Deploying to a free host

The backend is designed so a single `DATABASE_URL` env var overrides all the individual `DB_*` vars — this matches what Render, Railway, Heroku, Fly.io, and Neon all inject automatically.

### Render — one click via `render.yaml`

This repo ships with a **Render Blueprint** at [`render.yaml`](./render.yaml) that provisions both the Postgres database and the web service in one step.

1. Push this repo to GitHub.
2. Go to <https://dashboard.render.com/blueprints> → **New Blueprint Instance**.
3. Pick the `flowapprove-backend` repo.
4. Render reads `render.yaml` and shows you what it's about to create:
   - `flowapprove-db` — free Postgres 16
   - `flowapprove-backend` — free Docker web service with `DATABASE_URL` auto-linked
5. Click **Apply** → wait ~4 minutes for the first build.
6. Copy the web service URL (e.g. `https://flowapprove-backend.onrender.com`).
7. Deploy the **frontend on Vercel** (see [flowapprove-frontend/README.md](https://github.com/ThkSanidhya/flowapprove-frontend)), set `VITE_API_URL` to the Render URL + `/api`.
8. Back in Render, update `CORS_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to the Vercel URL and trigger a redeploy.

> **Free-tier caveat**: Render spins down the web service after 15 min of inactivity. The first request after idle takes ~30 seconds to wake up. That's Render, not a bug.

### Railway — manual

Railway doesn't read `render.yaml`. Create the service and Postgres manually, then wire `DATABASE_URL` from the Postgres add-on into the backend service. Everything else is identical to the Render env vars above.

### Anywhere else

As long as the host runs your `Dockerfile` and can inject `DATABASE_URL`, you're fine. See `flowapprove-docs/docs/deployment.md` for the full production checklist.

---

## Troubleshooting

**`django.db.utils.OperationalError: connection to server at "localhost"`** — Postgres isn't running, or `DB_HOST` / `DB_PORT` are wrong. Check `pg_isready -h 127.0.0.1 -p 5432` (Linux/macOS) or open **Services** and make sure `postgresql-x64-16` is running (Windows).

**`FATAL: password authentication failed for user "flowapprove"`** — password mismatch. On Linux/macOS try `PGPASSWORD=... psql -h 127.0.0.1 -U flowapprove flowapprove` to confirm the creds work outside Django.

**`Column 'organization_id' cannot be null` when creating a workflow** — the logged-in user's `organization` is NULL (usually a `createsuperuser` account). Register normally through the frontend, or assign the superuser to an org in the Django admin.

**CORS error in the browser console** — backend is running with `DJANGO_DEBUG=True` (wide-open CORS) or `CORS_ORIGINS` doesn't include the frontend URL. Check both.
