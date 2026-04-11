# CLAUDE.md — flowapprove-backend

Guidance for Claude Code when working in this repository.

## What this is

The Django + DRF backend for **FlowApprove**, a multi-tenant document approval workflow system. Sibling repos: `flowapprove-frontend/` (React SPA) and `flowapprove-docs/` (documentation).

## Commands

```bash
python manage.py migrate                    # apply migrations
python manage.py makemigrations api         # after model changes
python manage.py runserver                  # dev server :8000
python manage.py createsuperuser
python manage.py test api                   # full suite
python manage.py test api.tests.ClassName.test_method   # single test
```

## Architecture

Single Django app `api/` holds the entire domain. HTTP routes are function-based DRF views in `api/views.py`, wired in `api/urls.py`. Business logic lives directly in views; `api/utils.py` holds shared helpers (including `send_email_notification`) and `api/serializers.py` holds DRF serializers. Project module: `flowapprove_backend/`.

**Auth**: JWT via `rest_framework_simplejwt`. `AUTH_USER_MODEL = 'api.User'` — custom user with `USERNAME_FIELD = 'email'`, a `role` (`ADMIN` / `USER`), and an `Organization` FK.

**Multi-tenant**: every domain row is scoped by `organization`. See the golden rule below.

## Domain model (`api/models.py`)

- `Organization` owns `User`s, `Workflow`s, `Document`s.
- `Workflow` has ordered `WorkflowStep`s, each assigned to a `User`.
- `Document` references a `Workflow` and tracks `status` (`PENDING`/`APPROVED`/`REJECTED`) plus `current_step` (1-indexed).
- `DocumentApproval` records per-step decisions.
- `DocumentComment` (optionally page-anchored for PDFs), `DocumentHistory` (append-only audit log), and `DocumentVersion` (re-uploads after rejection) hang off `Document`.

Approve / reject / sendback endpoints advance or reset `current_step` and append to `DocumentApproval` + `DocumentHistory`. **Keep the three in sync inside a single `transaction.atomic()`.**

## Golden rules (MUST follow)

1. **Tenant scoping** — every query that touches `User`, `Workflow`, `Document`, or any child row MUST filter by `organization=request.user.organization`. Forgetting this is IDOR.
2. **Step authorization** — only the user tied to the current-step `DocumentApproval` may approve / reject / sendback.
3. **Atomic transitions** — wrap any change to `current_step` + `DocumentApproval.status` + `DocumentHistory` in `transaction.atomic()`. Use `select_for_update()` on rows you will mutate.
4. **Use `timezone.now()`**, never `datetime.now()`. `USE_TZ=True`.
5. **Validate workflow step users** belong to the requester's organization when creating / updating workflows.
6. **Env-driven config** — `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, and `DB_*` all come from environment variables (see `flowapprove_backend/settings.py`). Do not hardcode secrets.
7. **Upload constraints** — max 50 MB, MIME whitelist (`pdf`, `jpeg`, `png`, `doc`, `docx`). Randomize on-disk filenames with `uuid.uuid4().hex`.

## Storage

Uploads live in `MEDIA_ROOT/documents/` and `MEDIA_ROOT/versions/`. `Document.file_url` is stored alongside the `FileField`.

## Settings notes

`flowapprove_backend/settings.py` is dev-friendly:
- PostgreSQL via env vars (defaults: `flowapprove` db on localhost)
- `DEBUG` defaults to `True`; flip to `False` in prod
- `CORS_ALLOW_ALL_ORIGINS = True` — dev only; replace with an explicit allowlist before deploying
- SMTP creds still hardcoded; migrate to env vars before production

## When changing an API contract

Update `api/serializers.py` / `api/views.py` **and** the matching `src/services/*Service.js` in `flowapprove-frontend/frontend/` in the same change. There is no shared schema.

## Full documentation

See `flowapprove-docs/` for architecture diagrams, API reference, data model, deployment checklist, and the security model.
