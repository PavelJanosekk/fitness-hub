# Fitness Hub — agent guide

Self-hosted, mobile-first PWA: body metrics, gym logging (Strong replacement), marathon prep, and
Gemini-powered assistants. Single user, accessed over Tailscale (HTTPS via `tailscale serve`).

## Start here
1. `docs/PROGRESS.md` — current phase, checklist, decisions, open questions. **Read first, update after every meaningful step.**
2. `docs/SPEC.md` — the core specification (schema, API, UI, phases). Source of truth.
3. `docs/nutrition-module-spec.md` — Phase 5 nutrition module; its "Amendments" section overrides the original text.
4. `docs/plan-review-2026-10-17.md` — rationale behind spec changes + verified USDA/OFF API facts.

## Working agreements
- Do all work in the main session — no subagents or workflows.
- Propose spec/architecture changes with a recommendation and get a decision before editing the specs; record decisions in `docs/PROGRESS.md`.
- Execute phases in order (`docs/SPEC.md` §9) and verify each before moving on.
- Git: work on the `dev` branch, commit after each verified step, and never commit `.env` or anything in `data/`.

## Hard rules
- Backend: Python 3.12+, FastAPI, SQLModel, PostgreSQL 16 via psycopg 3 (`postgresql+psycopg://`).
- AI: ONLY `google-genai` (`from google import genai`). NEVER the deprecated `google-generativeai`.
- Gemini model ids come from env (`GEMINI_MODEL_FAST` / `GEMINI_MODEL_SMART`); never hardcode them.
- Schema changes go through Alembic migrations — never rely on `create_all`.
- Timestamps are `timestamptz` (UTC); "today"/day buckets use `APP_TZ` (Europe/Prague) via `app/timeutils.py`.
- Client-created rows (workouts, sets, meal logs/items, conversations) use client-generated UUIDs; create/update endpoints are idempotent upserts.
- Unknown ≠ 0: missing values stay null; aggregations report coverage.
- Intake (kcal/macros) lives only in `meal_logs`/`meal_log_items`, not in `DailyMetric`.
- Two separate assistants (coach, nutrition) on one shared Gemini runner. AI writes use the hybrid save flow: auto-save only on high-confidence matches, otherwise return a draft for 1-tap confirmation.
- UI copy and AI replies in Czech; code, identifiers, comments and docs in English.
- Frontend: React 18 + Vite + TypeScript, Tailwind, lucide-react, TanStack Query v5 (persisted mutations), recharts, react-router-dom, vite-plugin-pwa.

## Commands
Prod and dev are separate compose projects (E14). Plain `docker compose` means **prod** (`fitness-hub`, real data);
`./dev` wraps the dev project (`fitness-hub-dev`, its own DB). Develop, migrate and test only through `./dev`.
- Dev stack: `./dev up -d --build` (backend http://127.0.0.1:8020, Vite http://127.0.0.1:5173); refresh its DB from the newest prod backup with `scripts/seed-dev-db.sh`
- Migrations: `./dev exec app alembic upgrade head` / `./dev exec app alembic revision --autogenerate --rev-id 000N -m "<msg>"` (sequential ids)
- Tests & lint: `./dev exec app pytest`, `./dev exec app ruff check .`, frontend `npm run typecheck`
- Production: `docker compose up -d --build` (runs migrations on start); logs: `docker compose logs -f app`; backups/restore: `docs/operations.md`
- Health: `curl -f http://127.0.0.1:8010/api/health` (prod host port = `APP_PORT`, default 8010, localhost only; dev = 8020)
- HTTPS on the tailnet: `tailscale serve --bg 8010` (prod on :443), `tailscale serve --bg --https=8443 5173` (dev Vite on :8443). Needs sudo unless the user is the Tailscale operator.
- Fix any container startup traceback before finishing a phase.

## Dependencies
- Direct deps are pinned exactly in `backend/requirements.txt` / `requirements-dev.txt`. The full resolved set is frozen in `backend/constraints.txt`, and the Dockerfile installs with `-c constraints.txt`.
- Only use releases **at least 14 days old**, including transitive ones.
- To add or bump a dependency:
  1. Edit the requirements file.
  2. Temporarily empty `constraints.txt` and rebuild.
  3. `pip list --format=freeze --exclude pip` in the container.
  4. Check release dates on PyPI and cap anything too fresh.
  5. Write the freeze back to `constraints.txt` (keep its header), rebuild, and re-run tests.
- Tests use `httpx2` (starlette's TestClient deprecates plain `httpx`). Runtime HTTP calls (Strava, KT SDK) use `httpx`.

## Local environment notes
- `.env` exists (POSTGRES_*, DATABASE_URL with host `db`, GEMINI_API_KEY) — never print or commit it; `.env.example` documents the keys.
- Node and python3-venv are not installed on the host, so everything runs in containers (frontend in `node:22` from Phase 3).
- Host port 8000 belongs to **Portainer**. The server also runs Caddy, Home Assistant, Immich and others, so never stop or reconfigure containers outside the `fitness-hub` and `fitness-hub-dev` compose projects. The app uses `APP_PORT` (8010).
- Docker: user `biggys` is in the `docker` group. If a session still gets "permission denied" on the socket (it started before the group change), wrap commands in `sg docker -c "..."`.
- `data/` is gitignored. It holds import samples (the real Strong export is `data/imports/strong_workouts.csv`) and backups. Test fixtures derived from it must be anonymized slices.
- Devices: an iPhone (PWA, Apple Health steps via iOS Shortcut), a Galaxy Watch paired with an Android phone (Samsung Health → Health Connect forwarder), and Strava for runs. See `docs/SPEC.md` §6.5.
