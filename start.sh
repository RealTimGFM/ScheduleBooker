#!/usr/bin/env bash
set -e

# Run migrations if Flask-Migrate/Alembic is set up
flask db upgrade || true

# Start web server
exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 4 --timeout 120
