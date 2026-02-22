#!/bin/bash
set -e

echo "==> Running database migrations..."
alembic upgrade head

echo "==> Seeding database..."
python scripts/seed.py

echo "==> Starting Gunicorn..."
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT:-5000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
