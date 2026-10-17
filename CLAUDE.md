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
- Dev stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`
- Migrations: `docker compose exec app alembic upgrade head` / `alembic revision --autogenerate -m "<msg>"`
- Tests & lint: `docker compose exec app pytest`, `docker compose exec app ruff check .`, frontend `npm run typecheck`
- Production: `docker compose up -d --build`; logs: `docker compose logs -f app`
- Health: `curl -f http://localhost:8000/api/health`
- HTTPS on the tailnet: `tailscale serve --bg 8000`
- Fix any container startup traceback before finishing a phase.

## Local environment notes
- `.env` exists (POSTGRES_*, DATABASE_URL with host `db`, GEMINI_API_KEY) — never print or commit it; `.env.example` documents the keys.
- Node is not installed on the host; the frontend runs in a `node:22` container in dev.
- `data/` is gitignored — put import samples (Strong CSV, KT export) and backups there.
