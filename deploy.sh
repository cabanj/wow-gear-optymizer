#!/usr/bin/env bash
# Deploy wow-gear-optymizer on the VPS. Run from repo root on ovh-fra.
set -euo pipefail
cd /opt/wow-gear-optymizer

# 1. env
[ -f .env ] || cp .env.example .env
echo ">> edit /opt/wow-gear-optymizer/.env (BLIZZARD creds, SECRET_KEY, BASE_URL)"

# 2. postgres up first
docker compose up -d postgres
sleep 5

# 3. migrations (autogenerate against live DB if missing)
if [ -z "$(ls migrations/versions 2>/dev/null)" ]; then
  docker compose run --rm web alembic revision --autogenerate -m "initial schema" || true
fi
docker compose run --rm web alembic upgrade head

# 4. all services
docker compose up -d --build
docker compose ps
