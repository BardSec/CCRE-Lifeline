# RubricOps

A cybersecurity maturity assessment tool for K12 technology teams. Score your district
against a rubric, attach evidence to each control, turn gaps into tracked remediation
tasks, and export results as PDF or CSV.

## Features

- **Evaluations** — score each rubric item on a 1–5 maturity scale with a confidence
  level and notes, then finalize the evaluation when complete.
- **Built-in rubric** — the seeded *K12 Cybersecurity Framework* covers 15 controls
  across three domains:
  - Identity & Access Management (IAM-1 – IAM-5)
  - Data Protection & Privacy (DPP-1 – DPP-5)
  - Incident Response & Recovery (IRR-1 – IRR-5)
- **Evidence library** — upload supporting files (policies, screenshots, audit reports)
  with optional expiry dates. Files are served only through authenticated routes.
- **Remediation tasks** — auto-generate improvement tasks for every item scoring below
  a target maturity level, or create tasks manually.
- **Exports** — PDF report and CSV export per evaluation.
- **Weekly checks** — every Monday at 07:00 UTC, background jobs flag stale evidence,
  evidence expiring within 30 days, and overdue tasks (currently written to the app log).
- **Audit log** — logins, score changes, uploads, user management, and other key actions
  are recorded and viewable by admins.
- **Microsoft 365 sign-in** — users are created automatically on first login. A
  password-less dev login is available locally when SSO isn't configured.

## Roles

| Role | Can do |
|---|---|
| `admin` | Everything, plus user management, tenant settings, and the audit log |
| `evaluator` | Create and finalize evaluations, generate tasks, upload evidence |
| `contributor` | Update scores, upload evidence, update tasks |
| `viewer` | Read-only access |

Emails listed in `ADMIN_EMAILS` get the admin role on login. Everyone else gets
`DEFAULT_USER_ROLE` (default `viewer`), which an admin can change under **Admin → Users**.

Each deployment serves one organization: everyone who signs in joins the tenant
created on first start.

## Tech Stack

- Python 3.11 / Flask 3 / Gunicorn
- PostgreSQL 15 + SQLAlchemy 2 (Flask-SQLAlchemy) + Alembic (Flask-Migrate)
- Authlib (Microsoft Entra ID OIDC) + Flask-Login
- Flask-WTF (CSRF protection)
- Flask-Limiter (login rate limiting)
- APScheduler (in-process background jobs)
- ReportLab (PDF export)
- Docker Compose (`web` + `db`)

## Quick Start

### Local development

```bash
make dev
```

The first run copies `.env.example` to `.env`. Set `SECRET_KEY` (the app won't
start without it), then run `make dev` again. Leave the `AZURE_*` values blank:
the login page then shows a **dev login** that signs you in with just an email
address. Use an address from `ADMIN_EMAILS` to get the admin role.

`make dev` runs Flask's debug server with hot reload and exposes Postgres on
`127.0.0.1:5440`. The app is at http://localhost:5000, or at whatever port
`WEB_PORT` is set to (macOS uses port 5000 for AirPlay, so you may need to change it).

On every start the container automatically:

1. Applies database migrations (`flask db upgrade`)
2. Seeds the organization and the K12 rubric if they don't exist (`flask seed`)
3. Starts the app (Gunicorn under `make up`, the Flask dev server under `make dev`)

### Production

1. **Register an app in Microsoft Entra ID.** In the Azure portal, go to
   **App registrations → New registration**:
   - Redirect URI (Web): `https://your-domain/auth/callback`
   - Create a client secret under **Certificates & secrets**
   - Note the **Application (client) ID** and **Directory (tenant) ID**
2. **Fill in `.env`:** `SECRET_KEY`, all three `AZURE_*` values, `ADMIN_EMAILS`,
   `ALLOWED_DOMAINS`, a strong `POSTGRES_PASSWORD` (also in `DATABASE_URL`), and
   `BEHIND_PROXY=true`.
3. **Start it** with `make up` and point your Cloudflare Tunnel at
   `http://localhost:${WEB_PORT}`.

See [SECURITY.md](SECURITY.md) for the full hardening checklist.

### Make targets

| Command | Description |
|---|---|
| `make dev` | Start with hot reload and the dev login (foreground) |
| `make up` | Build and start the production containers |
| `make down` | Stop the containers |
| `make logs` | Follow the web container logs |
| `make shell` | Open a shell in the web container |
| `make test` | Run pytest inside the web container |
| `make migrate m="description"` | Generate a migration after changing `app/models.py` |
| `make upgrade` | Apply pending migrations |

## Environment Variables

See `.env.example` for the full annotated list.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | **Required**, 32+ characters. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEBUG` | `false` | Flask debug mode |
| `WEB_PORT` | `5000` | Host port, bound to `127.0.0.1` |
| `BEHIND_PROXY` | `false` | Set to `true` when deployed behind Cloudflare Tunnel. Trusts `X-Forwarded-*` headers, forces secure cookies, and refuses to start without SSO |
| `COOKIE_SECURE` | `true` | Send the session cookie over HTTPS only (the dev compose file turns it off) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `rubricops` / `rubricops` / `changeme` | PostgreSQL container credentials |
| `DATABASE_URL` | — | SQLAlchemy connection string, e.g. `postgresql+psycopg2://rubricops:changeme@db:5432/rubricops` |
| `AZURE_TENANT_ID` | — | Entra ID directory (tenant) ID. Set all three `AZURE_*` values or none |
| `AZURE_CLIENT_ID` | — | Entra ID app (client) ID |
| `AZURE_CLIENT_SECRET` | — | Entra ID client secret |
| `ADMIN_EMAILS` | — | Comma-separated emails granted admin on login |
| `ALLOWED_DOMAINS` | — | Comma-separated email domains allowed to sign in. Blank allows any account that authenticates |
| `DEFAULT_USER_ROLE` | `viewer` | Role for new non-admin users: `viewer`, `contributor`, or `evaluator` |
| `LOGIN_RATE_LIMIT` | `10 per minute` | Rate limit on the login routes, per IP |
| `STORAGE_BACKEND` | `local` | Evidence storage backend. Only `local` is supported today |
| `EVIDENCE_DIR` | `/app/evidence` | Where uploaded evidence is stored (a Docker volume) |
| `MAX_UPLOAD_BYTES` | `52428800` | Max upload size (50 MB) |
| `SCHEDULER_ENABLED` | `true` | Run the weekly evidence/task checks |
| `GUNICORN_WORKERS` | `2` | Gunicorn worker count |
| `SEED_TENANT_NAME` | `Lakeside School District` | Name of the organization created on first start (rename it later under Admin → Tenant Settings) |
| `TEST_DATABASE_URL` | `DATABASE_URL` + `_test` | Database used by the test suite (created automatically) |

## Deployment

The app is designed to run behind a reverse proxy such as Cloudflare Tunnel, which
terminates TLS. The app itself never handles TLS. Set `BEHIND_PROXY=true` so that
redirect URIs use `https://` and the audit log records real client IPs. The web
port is only published on `127.0.0.1`.

Persistent data lives in two Docker volumes:

- `postgres_data` — the database
- `evidence_data` — uploaded evidence files

Back up both. Evidence files are not stored in the database.

A health check endpoint is available at `/healthz`.

## Project Structure

```
app/
  __init__.py        # create_app() factory, error pages, `flask seed` command
  extensions.py      # db, migrate, csrf, login_manager, oauth, limiter
  config.py          # Environment-based config + startup validation
  auth.py            # Microsoft OIDC sign-in, dev login, /healthz
  models.py          # SQLAlchemy models
  blueprints/        # Thin routes: dashboard, evaluations, evidence, tasks, admin
  services/          # Business logic, validation, storage, seed data, exports
  jobs/scheduler.py  # Weekly APScheduler jobs
  templates/         # Jinja2 templates
migrations/          # Alembic migrations (Flask-Migrate)
tests/               # pytest (runs against PostgreSQL)
```

Routes stay thin: they parse the request, call a service in `app/services/`, and
render or redirect. Tenant scoping, validation, and audit logging live in the services.

## Database Migrations

All schema changes go through Flask-Migrate (Alembic):

```bash
make migrate m="add foo to evaluations"   # flask db migrate -m "..."
make upgrade                              # flask db upgrade
```

Review the generated file in `migrations/versions/` before applying it.

## Testing

```bash
make dev     # in one terminal (or make up)
make test    # in another
```

Tests run against a separate `<db>_test` PostgreSQL database, which is created
automatically. To run them from your host instead, point `TEST_DATABASE_URL` at
the dev database port: `postgresql+psycopg2://rubricops:changeme@localhost:5440/rubricops_test`.

## Security

See [SECURITY.md](SECURITY.md) for security controls and production hardening steps.
