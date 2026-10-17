# Operations

Running the production stack on the server. Commands run from the repo root.

## Backups

The `backup` compose service (`scripts/backup.sh`, image `postgres:16-alpine`) writes a `pg_dump --format=custom`
of the whole database every day at `BACKUP_HOUR` (default 3:00, `APP_TZ`). If the newest dump is over 24 h old
(first start, or the server was off at that hour), it backs up right away instead.

```
data/backups/                 # BACKUP_DIR (default ./data/backups, gitignored)
├── daily/fitness-hub-2026-10-17.dump     # newest 7 kept
├── weekly/fitness-hub-2026-W42.dump      # first dump of each ISO week, newest 4 kept
└── monthly/fitness-hub-2026-10.dump      # first dump of each month, newest 6 kept
```

- Weekly and monthly copies are hard links to the daily file, so they take no extra space until the daily one
  is pruned. A full dump is about 160 KB (Oct 2026).
- Files belong to `HOST_UID` with mode 600.
- `docker compose ps` shows the service as unhealthy when the newest dump is over 26 h old.
  Logs: `docker compose logs backup`.
- These dumps sit on the same disk as the database. They protect against bad migrations, mistakes and DB
  corruption, but not against losing the disk. Point `BACKUP_DIR` at another disk or a NAS mount, or copy
  `data/backups/` off the server regularly.

Back up right now (for example before a risky migration):

```sh
docker compose exec backup sh -c 'pg_dump --format=custom --file=/backups/manual-$(date +%F-%H%M).dump'
```

Manual dumps live in the top level of `BACKUP_DIR` and are never pruned.

### Restore

`--clean` drops and recreates every object in the dump, so the database ends up exactly as it was at backup
time (checked against a real-data copy: all tables, extensions and `f_unaccent()` come back).

```sh
docker compose stop app      # nothing may write during the restore
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' \
  < data/backups/daily/fitness-hub-2026-10-17.dump
docker compose start app     # runs any newer migrations on start
```

To look inside a dump without touching the live data, restore it into a scratch database:

```sh
docker compose exec db createdb -U fitness restore_check
docker compose exec -T db pg_restore -U fitness -d restore_check --no-owner < data/backups/daily/<file>.dump
docker compose exec db psql -U fitness -d restore_check     # ... then: dropdb -U fitness restore_check
```
