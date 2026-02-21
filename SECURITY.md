# Security Guide — RubricOps

This document describes the security controls built into RubricOps and the
configuration steps an administrator must perform before running it in production.

---

## How Data Is Protected

### Authentication
- **Email + password** authentication with bcrypt hashing (cost factor 12).
- Sessions are stored as **JWT tokens in httpOnly, SameSite=Lax cookies**, preventing JavaScript
  access and CSRF from cross-origin pages.
- **Rate limiting** is enforced on `POST /login`: 10 requests per minute per IP.
- Tokens expire after **8 hours** (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`).

### Authorization (RBAC)
| Role | Capabilities |
|---|---|
| `admin` | Full access: user management, tenant settings, audit log |
| `evaluator` | Create/finalize evaluations, upload evidence, manage tasks |
| `contributor` | Update scores, upload evidence, update tasks |
| `viewer` | Read-only access to evaluations, evidence list, tasks |

- **Every database query is scoped to `tenant_id`** — no cross-tenant data leakage is possible
  through the application layer.
- Role checks are enforced via FastAPI dependency injection (`require_roles`), not ad-hoc conditionals.

### Evidence File Storage
- Files are stored in **MinIO** (local S3-compatible object storage), not the database.
- The database stores only **metadata** (key, filename, content type, size, uploader, timestamps).
- Object keys are **tenant-prefixed** (`<tenant_id>/evidence/<uuid>.<ext>`), preventing path
  traversal between tenants.
- Uploads are validated for:
  - **Content type** (allowlist; see `ALLOWED_CONTENT_TYPES` in `.env`)
  - **File size** (default 50 MB; set `MAX_UPLOAD_BYTES`)
- MinIO bucket access is set to **private** (no public object URLs).

### Audit Logging
- Every significant action (login, score update, evidence upload/delete, user management, etc.)
  is written to the `audit_logs` table with: actor, action, entity, timestamp, IP address.
- Logs are tenant-scoped and visible only to `admin` users.

### Secrets Management
- All secrets are loaded from **environment variables** (`.env` file, never committed to source).
- No secrets appear in logs, error messages, or HTTP responses.

---

## Production Hardening Checklist

### 1. Secrets — REQUIRED before going live

```bash
# Generate a strong SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Set strong PostgreSQL password
POSTGRES_PASSWORD=<strong-random>

# Set strong MinIO credentials
MINIO_ROOT_USER=<non-default>
MINIO_ROOT_PASSWORD=<strong-random>
```

- Replace all default values in `.env` before first deployment.
- `SECRET_KEY` rotation invalidates all active sessions.

### 2. HTTPS — REQUIRED

- Place a **reverse proxy** (Nginx, Caddy, Traefik) in front of the web container.
- Configure **TLS termination** at the proxy layer.
- Set `secure=True` on the session cookie (in `app/auth/router.py`, line with `set_cookie`).
- Redirect all HTTP → HTTPS at the proxy level.

### 3. Network isolation

- MinIO should **not** be exposed to the public internet.
  Remove the port mapping in `docker-compose.yml` or restrict it to `127.0.0.1`.
- PostgreSQL should **not** be exposed externally. The `db` service has no published ports
  by default — keep it that way.

### 4. Backups

- **PostgreSQL**: schedule `pg_dump` of the `rubricops` database to off-site storage.
- **MinIO**: use `mc mirror` to replicate the bucket to a secondary storage location or
  configure MinIO replication.

### 5. Token & session security

- Reduce `ACCESS_TOKEN_EXPIRE_MINUTES` if higher security is needed (e.g., `60` for 1-hour sessions).
- There is no server-side token revocation in the MVP. For logout, the cookie is deleted client-side.
  Add a token blocklist (Redis-backed) in future iterations.

### 6. File upload security

- Review and tighten `ALLOWED_CONTENT_TYPES` if your district does not need all permitted types.
- The `MAX_UPLOAD_BYTES` limit (default 50 MB) is enforced server-side. Set this to the minimum
  needed for your evidence documents.

### 7. Login rate limiting

- The default rate limit is **10 login attempts per minute per IP**.
- Adjust `LOGIN_RATE_LIMIT` in `.env` (e.g., `5/minute`) for higher security.
- For additional brute-force protection, add an account lockout mechanism or a CAPTCHA.

### 8. Dependency updates

- Run `pip list --outdated` regularly and update packages, especially security-critical ones
  (`python-jose`, `passlib`, `fastapi`).

---

## SSO Roadmap (Next Steps)

The MVP uses email + password. The following SSO integrations are planned for future releases:

- **Microsoft 365 / Azure AD**: OAuth 2.0 / OIDC via `msal` or `python-social-auth`.
  Users can log in with their district Microsoft accounts.
- **Google Workspace**: OAuth 2.0 / OIDC via `authlib`.
  Users can log in with their district Google accounts.

Both integrations will be additive — email/password will remain as a fallback for
service accounts and emergency admin access.

---

## Reporting Vulnerabilities

Report security vulnerabilities responsibly by opening a private GitHub security advisory
or contacting the maintainers directly. Do not open public issues for security bugs.
