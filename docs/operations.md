# Operations

Running the app on the server. Commands run from the repo root.

## Two stacks (E14)

| | Prod | Dev |
|---|---|---|
| Command | `docker compose …` | `./dev …` (adds `docker-compose.dev.yml`) |
| Compose project | `fitness-hub` | `fitness-hub-dev` |
| Database | volume `fitness-hub_pgdata`, the real data | volume `fitness-hub-dev_pgdata`, a copy (`scripts/seed-dev-db.sh`) |
| App | built image (API + SPA), `127.0.0.1:8010` | `uvicorn --reload` on the bind-mounted code, `127.0.0.1:8020` |
| Frontend | served by the app | Vite on `127.0.0.1:5173` |
| Scheduler (Strava, KB sync, auto-finish) | on | off |
| Backups | daily | none |
| Tailnet URL | `https://biggyserver.tailfff1d3.ts.net` | `https://biggyserver.tailfff1d3.ts.net:8443` |

Both stacks can run at the same time. They are separate origins on the phone (the port is part of the origin),
so the dev PWA never shares the service worker, offline queue or active workout with the real one.

### Deploy a new version to prod

```sh
git switch dev && git pull                # or whichever commit should go live
docker compose up -d --build              # rebuilds the image; the app runs migrations on start
docker compose ps                         # app, db, backup: all (healthy)
docker compose logs --tail 50 app         # no tracebacks
```

Before a release with a migration, take a manual backup (see below). Phones pick up the new frontend on their
next load: `index.html` and `sw.js` are served `no-cache`, and the PWA updates itself.

### Dev stack

```sh
./dev up -d --build          # db, app (8020), frontend (5173)
scripts/seed-dev-db.sh       # optional: replace the dev DB with the newest prod backup (Strava tokens dropped)
./dev exec app pytest        # tests use their own <db>_test database inside the dev Postgres
./dev down                   # stop dev; prod keeps running
```

## HTTPS on the tailnet (E13)

`tailscale serve` terminates HTTPS with a Tailscale-issued certificate and proxies to localhost:

```sh
sudo tailscale serve --bg 8010                 # https://<host>.<tailnet>.ts.net       → prod
sudo tailscale serve --bg --https=8443 5173    # https://<host>.<tailnet>.ts.net:8443  → dev Vite
tailscale serve status
```

The config survives reboots. `sudo` is needed unless the user was made the Tailscale operator once
(`sudo tailscale set --operator=$USER`). That also lets any process running as that user change the serve
config, so it is optional. Only tailnet devices can reach these URLs (no Funnel).

## Integrations

Server side, `.env` has `PUBLIC_BASE_URL` (the tailnet URL, used for the Strava OAuth redirect) and
`WEBHOOK_TOKEN` (shared secret for the webhooks; read it with `grep '^WEBHOOK_TOKEN=' .env`). After changing
`.env`, run `docker compose up -d app`. Setup per source:

- [Strava](integrations/strava.md): runs, HR, stream metrics.
- [iOS Shortcut](integrations/ios-shortcut.md): iPhone steps from Apple Health.
- [Health Connect](integrations/health-connect.md): watch steps and sleep via Life Dashboard Companion.

- **Data export (E40)** into the analysis repo: create a fine-grained token on GitHub (Settings → Developer
  settings → Fine-grained tokens) limited to that repo, permission **Contents: Read and write**, and set
  `GITHUB_TOKEN` and `EXPORT_REPO=owner/repo` in `.env`. The export runs daily after `EXPORT_HOUR` and on
  **Exportovat teď**; a public repo asks for confirmation first.

**Nastavení** shows the state of each source: Strava connection and last sync, plus the last payload per
webhook source.

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
