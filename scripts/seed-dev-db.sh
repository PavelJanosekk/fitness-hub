#!/bin/sh
# Replace the dev database with a copy of the newest prod backup (E14), minus the Strava OAuth tokens:
# Strava rotates refresh tokens, so two stacks refreshing the same pair would log each other out.
# Usage: scripts/seed-dev-db.sh [path/to/backup.dump]
set -eu
cd "$(dirname "$0")/.."

dump=${1:-$(ls -1 data/backups/daily/*.dump 2>/dev/null | sort | tail -n 1)}
if [ -z "$dump" ] || [ ! -f "$dump" ]; then
    echo "No backup found in data/backups/daily; is the prod backup service running? (docker compose ps)" >&2
    exit 1
fi

./dev up -d --wait db
./dev stop app
./dev exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' \
    < "$dump"
./dev exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -qc "DELETE FROM integration_tokens"'
./dev up -d app
echo "Dev DB seeded from $dump"
