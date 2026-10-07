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
- **Microsoft 365 sign-in** — users are created automatically on first login.

## Roles

| Role | Can do |
|---|---|
| `admin` | Everything, plus user management, tenant settings, and the audit log |
| `evaluator` | Create and finalize evaluations, generate tasks, upload evidence |
| `contributor` | Update scores, upload evidence, update tasks |
| `viewer` | Read-only access |

Emails listed in `ADMIN_EMAILS` get the admin role on login. Everyone else gets
`DEFAULT_USER_ROLE` (default `viewer`), which an admin can change under **Admin → Users**.

## Tech Stack

- Python 3.11 / Flask 3 / Gunicorn
- PostgreSQL 15 + SQLAlchemy 2 + Alembic
- Authlib (Microsoft Entra ID OIDC) + Flask-Login
- Flask-Limiter (login rate limiting)
- APScheduler (in-process background jobs)
- ReportLab (PDF export)
- Docker Compose (`web` + `db`)

## Quick Start

### 1. Register an app in Microsoft Entra ID

In the Azure portal, go to **App registrations → New registration**:

- Redirect URI (Web): `https://your-domain/auth/callback`
  (for local dev: `http://localhost:5000/auth/callback`)
- Create a client secret under **Certificates & secrets**
- Note the **Application (client) ID** and **Directory (tenant) ID**

### 2. Configure and run

```bash
make up
```

The first run copies `.env.example` to `.env`. Fill in the Azure values, `SECRET_KEY`,
and `ADMIN_EMAILS`, then run `make up` again.

On startup the container automatically:

1. Runs Alembic migrations (`alembic upgrade head`)
2. Seeds the tenant and the K12 rubric (`scripts/seed.py`, safe to re-run)
3. Starts Gunicorn on port 5000

Open http://localhost:5000 and sign in with Microsoft.

> For local HTTP-only development, set `COOKIE_SECURE=false` in `.env`, or the
> session cookie won't be sent.

### Make targets

| Command | Description |
|---|---|
| `make up` | Build and start the containers |
| `make down` | Stop the containers |
| `make logs` | Follow the web container logs |
| `make shell` | Open a shell in the web container |
| `make test` | Run pytest inside the web container |

## Environment Variables

See `.env.example` for the full annotated list.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | — | Flask session secret. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DEBUG` | `false` | Flask debug mode |
| `WEB_PORT` | `5000` | Host port mapped to the web container |
| `COOKIE_SECURE` | `true` | Send the session cookie over HTTPS only |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `rubricops` / `rubricops` / `changeme` | PostgreSQL container credentials |
| `DATABASE_URL` | `postgresql+psycopg2://rubricops:changeme@db:5432/rubricops` | SQLAlchemy connection string |
| `AZURE_CLIENT_ID` | — | Entra ID app (client) ID |
| `AZURE_CLIENT_SECRET` | — | Entra ID client secret |
| `AZURE_TENANT_ID` | `common` | Directory (tenant) ID, or `common` |
| `ADMIN_EMAILS` | — | Comma-separated emails granted admin on login |
| `ALLOWED_DOMAINS` | — | Comma-separated email domains allowed to sign in. Blank allows any Microsoft account |
| `DEFAULT_USER_ROLE` | `viewer` | Role for new non-admin users: `viewer`, `contributor`, or `evaluator` |
| `EVIDENCE_DIR` | `/app/evidence` | Where uploaded evidence is stored (a Docker volume) |
| `MAX_UPLOAD_BYTES` | `52428800` | Max upload size (50 MB) |
| `LOGIN_RATE_LIMIT` | `10 per minute` | Rate limit on the login route |
| `SEED_TENANT_NAME` | `Lakeside School District` | Name of the organization created by the seed script |
| `GUNICORN_WORKERS` | `2` | Gunicorn worker count |

## Deployment

The app is designed to run behind a reverse proxy such as Cloudflare Tunnel, which
terminates TLS. The app itself never handles TLS.

Persistent data lives in two Docker volumes:

- `postgres_data` — the database
- `evidence_data` — uploaded evidence files

Back up both. Evidence files are not stored in the database.

A health check endpoint is available at `/healthz`.

## Project Structure

```
app/
  __init__.py        # create_app() factory
  auth.py            # Microsoft OIDC login/logout, /healthz
  config.py          # Environment-based config
  models.py          # SQLAlchemy models
  blueprints/        # dashboard, evaluations, evidence, tasks, admin
  services/          # storage, PDF and CSV export
  jobs/scheduler.py  # Weekly APScheduler jobs
  templates/         # Jinja2 templates
alembic/             # Database migrations
scripts/seed.py      # Tenant and rubric seed data
tests/               # pytest
```

## Database Migrations

All schema changes go through Alembic:

```bash
docker compose exec web alembic revision --autogenerate -m "description"
docker compose exec web alembic upgrade head
```

## Testing

```bash
make test
```

## Security

See [SECURITY.md](SECURITY.md) for security controls and production hardening steps.
