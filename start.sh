#!/usr/bin/env bash
set -euo pipefail

# Ensure DB schema + seeds exist (works for SQLite locally and Neon Postgres in prod)
python create_db.py

# Start web server
exec gunicorn wsgi:app \
  --bind 0.0.0.0:${PORT:-10000} \
  --workers 2 \
  --threads 4 \
  --timeout 120
