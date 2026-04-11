# FlowApprove Backend

Django + DRF API for **FlowApprove**, a multi-tenant document approval workflow system.

Sibling repos: [flowapprove-frontend](https://github.com/ThkSanidhya/flowapprove-frontend) · [flowapprove-docs](https://github.com/ThkSanidhya/flowapprove-docs)

The easiest way to run the full stack is from the [**meta-repo**](https://github.com/ThkSanidhya/flowapprove) with Docker. Keep reading if you want to run the backend natively.

---

## Quickstart — Docker

From the parent directory (with sibling `flowapprove-frontend/` cloned):

```bash
docker compose up --build
```

This starts MySQL 8 + the backend (gunicorn) + the frontend (nginx). See the top-level meta-repo README for details.

---

## Quickstart — native (Linux / macOS)

### Prerequisites

- **Python 3.12+**
- **MySQL 8+** running locally (or reachable via env vars)

### 1. Clone and create a virtualenv

```bash
git clone https://github.com/ThkSanidhya/flowapprove-backend.git
cd flowapprove-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create a MySQL database

```bash
mysql -u root -p -e "CREATE DATABASE flowapprove CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 3. Set environment variables

Copy the template and fill in real values:

```bash
cp .env.example .env
# edit .env — at minimum set DB_PASSWORD and DJANGO_SECRET_KEY
```

Then load it:

```bash
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

### Prerequisites

- **Python 3.12+** from <https://www.python.org/downloads/> (during install, tick **"Add python.exe to PATH"**)
- **MySQL 8+** from <https://dev.mysql.com/downloads/installer/>
- **Microsoft C++ Build Tools** (required by `mysqlclient`): <https://visualstudio.microsoft.com/visual-cpp-build-tools/> → install "Desktop development with C++"

> **If the C++ Build Tools are painful**, just use Docker Desktop. It's what we recommend for Windows users.

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

### 2. Create a MySQL database

Open **MySQL Workbench** or **MySQL Command Line Client** and run:

```sql
CREATE DATABASE flowapprove CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. Set environment variables (PowerShell)

```powershell
$env:DJANGO_SECRET_KEY = "dev-only-secret"
$env:DJANGO_DEBUG = "True"
$env:DB_NAME = "flowapprove"
$env:DB_USER = "root"
$env:DB_PASSWORD = "your-mysql-password"
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "3306"
```

(Command Prompt uses `set DB_PASSWORD=your-mysql-password` instead.)

To persist them between sessions, either edit `.env` and use a loader like `dotenv-cli`, or set them in System Properties → Environment Variables.

### 4. Migrate and run

```powershell
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```

The API is now available at **http://127.0.0.1:8000/**.

---

## Useful endpoints

| URL                               | Purpose                                   |
|-----------------------------------|-------------------------------------------|
| `http://localhost:8000/api/docs/` | Swagger UI — interactive API explorer     |
| `http://localhost:8000/api/redoc/`| Redoc reference documentation             |
| `http://localhost:8000/api/schema/` | Raw OpenAPI 3 YAML                      |
| `http://localhost:8000/healthz`   | Liveness + DB probe (no auth)             |
| `http://localhost:8000/admin/`    | Django admin (use your superuser account) |

---

## Commands cheat sheet

| Task                      | Command |
|---------------------------|---------|
| Apply migrations          | `python manage.py migrate` |
| Create a migration        | `python manage.py makemigrations api` |
| Dev server                | `python manage.py runserver` |
| Run tests (SQLite, no MySQL needed) | `python manage.py test api --settings=flowapprove_backend.settings_test` |
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

## Troubleshooting

**`MySQLdb.OperationalError: (1045, "Access denied for user 'root'@'localhost'")`** — your MySQL password is wrong or `DB_PASSWORD` isn't exported. On Windows check `$env:DB_PASSWORD` (PowerShell) or `echo %DB_PASSWORD%` (cmd).

**`MySQLdb.OperationalError: (1366, "Incorrect string value: '\xF0\x9F...'")`** — your database is using `latin1` or 3-byte `utf8` instead of `utf8mb4`. Fix with:
```sql
ALTER DATABASE flowapprove CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**`Column 'organization_id' cannot be null` when creating a workflow** — the logged-in user's `organization` is NULL (usually a `createsuperuser` account). Register normally through the frontend, or assign the superuser to an org in the Django admin.

**`mysqlclient` wheel build fails on Windows** — install Microsoft C++ Build Tools, or switch to Docker Desktop.

**`CORS error in browser`** — backend has `CORS_ALLOW_ALL_ORIGINS=True` in dev. Confirm `DJANGO_DEBUG=True` in your env.
