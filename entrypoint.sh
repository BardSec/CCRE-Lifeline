#!/bin/bash
# Apply migrations, create default data if missing, then start the given command.
set -e

echo "==> Running database migrations..."
flask db upgrade

echo "==> Seeding default data..."
flask seed

echo "==> Starting: $*"
exec "$@"
