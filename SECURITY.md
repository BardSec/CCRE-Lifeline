# Security Guide — RubricOps

This document describes the security controls built into RubricOps and what an
administrator must configure before running it in production.

RubricOps stores a district's cybersecurity self-assessment: maturity scores, the
gaps that remain, and evidence files such as policies and audit reports. That is a
roadmap of the district's weaknesses, so treat the database and the evidence
volume as **confidential**.

---

## How Data Is Protected

### Authentication
- **Microsoft Entra ID (OIDC)** via Authlib. RubricOps never sees or stores passwords.
- Users are created automatically on their first successful sign-in.
- `ALLOWED_DOMAINS` restricts sign-in to district email domains. Emails in
  `ADMIN_EMAILS` are always allowed and are given the admin role.
- **Dev login fallback:** when the three `AZURE_*` variables are unset, the
  login page offers a password-less, email-only sign-in for local development.
  The app **refuses to start** if `BEHIND_PROXY=true` and SSO isn't configured,
  and also refuses a partial SSO configuration, so the dev login can't be
  exposed on a deployed instance by accident.
- **Sessions** are signed Flask cookies (`HttpOnly`, `SameSite=Lax`, `Secure`
  when `COOKIE_SECURE` or `BEHIND_PROXY` is set) that expire after 8 hours. The
  session is cleared at sign-in (session fixation) and at sign-out.
- Deactivating a user ends their session on the next request.
- **Rate limiting:** the login routes are limited to `LOGIN_RATE_LIMIT` per IP
  (default 10 per minute). Limits are held in memory, per Gunicorn worker.

### Authorization (RBAC)
| Role | Capabilities |
|---|---|
| `admin` | Full access: user management, tenant settings, audit log |
| `evaluator` | Create/finalize evaluations, generate tasks, upload evidence |
| `contributor` | Update scores, upload evidence, create/update tasks |
| `viewer` | Read-only access to evaluations, evidence, and tasks |

- Enforced on each route with the `@role_required` decorators in
  `app/blueprints/helpers.py`.
- Admins can't change their own role or deactivate themselves, so the
  organization can't be left without an admin.
- Every query is scoped to the signed-in user's `tenant_id`, and references in
  form input (task owners, evaluations) are checked against the same tenant.
  RubricOps is deployed as **one organization per instance**: all users join
  the single tenant created by `flask seed`.

### CSRF
- Flask-WTF `CSRFProtect` is enabled globally. Every state-changing route is a
  POST that requires the session's CSRF token, including sign-out.

### Evidence File Storage
- Files are stored on a Docker volume (`evidence_data`, mounted at `EVIDENCE_DIR`),
  not in the database. The database stores only metadata.
- Files are only ever served through the authenticated, tenant-scoped download
  route, and every download is written to the audit log.
- Storage keys are generated server-side (`<tenant_id>/evidence/<uuid>.<ext>`).
  The extension is reduced to 1–10 lowercase alphanumerics, and every path is
  checked to stay inside `EVIDENCE_DIR`, so a crafted filename can't write
  outside the evidence directory.
- Uploads are validated for content type (allowlist in `app/config.py`) and
  size (`MAX_UPLOAD_BYTES`, default 50 MB; oversized requests are rejected
  before being read).

### Exports
- PDF and CSV exports are tenant-scoped. CSV cells containing user-entered text
  are prefixed with `'` when they start with `=`, `+`, `-` or `@`, so they
  open as text in Excel rather than as formulas.

### Audit Logging
- Sign-ins, evaluation and score changes, task changes, evidence
  upload/download/delete, user management, and tenant settings changes are
  recorded with actor, timestamp, client IP, and details.
- Admins can review the log under **Admin → Audit Log**.

### Input Validation
- Form input (ids, dates, numbers, enum choices) is validated in the service
  layer, so bad input returns a 400 page, not a server error.

---

## Production Hardening Checklist

### 1. Configuration
```env
SECRET_KEY=<64 hex chars from: python -c "import secrets; print(secrets.token_hex(32))">
BEHIND_PROXY=true
AZURE_TENANT_ID=<your directory (tenant) id>   # not "common"
AZURE_CLIENT_ID=<app registration client id>
AZURE_CLIENT_SECRET=<client secret>
ALLOWED_DOMAINS=<your district domain(s)>
ADMIN_EMAILS=<the people who should administer RubricOps>
POSTGRES_PASSWORD=<strong random value, also used in DATABASE_URL>
```
- The app won't start with a missing or placeholder `SECRET_KEY`.
- Rotating `SECRET_KEY` signs everyone out.
- Use your own tenant ID rather than `common`. If you must use `common`,
  `ALLOWED_DOMAINS` is the only thing keeping outside accounts out.

### 2. Network
- Run behind **Cloudflare Tunnel** (or another TLS-terminating reverse proxy).
  The app never terminates TLS itself.
- The web port is published on `127.0.0.1` only, and PostgreSQL isn't published
  at all in `docker-compose.yml`. Keep it that way. (`docker-compose.dev.yml`
  exposes Postgres on `127.0.0.1:5440` for local tests only.)
- Consider Cloudflare Access in front of the tunnel for an additional layer.

### 3. Entra ID app registration
- Redirect URI: `https://<your-domain>/auth/callback`
- Only the default `openid email profile` scopes are requested. No Graph API
  permissions are needed.
- Set a calendar reminder for the client secret's expiry.

### 4. Backups
- **PostgreSQL:** schedule `pg_dump` of the `rubricops` database to off-site storage.
- **Evidence:** back up the `evidence_data` volume on the same schedule. The
  database alone doesn't contain the files.
- Both backups contain sensitive security information; encrypt them.

### 5. File uploads
- Narrow `ALLOWED_CONTENT_TYPES` in `app/config.py` if your district doesn't
  need every permitted type.
- Lower `MAX_UPLOAD_BYTES` to what your evidence actually needs.

### 6. Dependency updates
- Run `pip list --outdated` in the container regularly, prioritizing Flask,
  Authlib, Flask-WTF, Werkzeug, and SQLAlchemy.

---

## Known Limitations

- Rate limits and the weekly background jobs run per Gunicorn worker (in memory),
  not shared across workers.
- Stale/expiring evidence and overdue task alerts are written to the app log only;
  there are no email notifications yet.
- No Content-Security-Policy header yet. The templates use inline scripts and
  styles, which would need to move to static files first.

---

## Reporting Vulnerabilities

Report security vulnerabilities by opening a private GitHub security advisory or by
contacting the maintainers directly. Don't open public issues for security bugs.
