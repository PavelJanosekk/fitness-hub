# Public app — stack plan

Planning notes for a multi-user, public version of Fitness Hub (friends first, more people later).
It will live in a **new repo**; modules are ported from Fitness Hub one at a time. Fitness Hub
itself stays the single-user personal app.

Status: brainstorming the stack step by step (started 2026-10-22).

## Decisions

| # | Topic | Decision |
|---|---|---|
| P1 | Audience / budget / ops | 5–20 friends in year 1, designed to grow; free now with a clean upgrade path to paid tiers; managed DB preferred (no 3 a.m. DB pages) |
| P2 | App hosting | The user's home server for now, as a separate compose project; everything containerized and env-configured so moving to a VPS / Cloud Run is a redeploy |
| P3 | Database | Supabase Postgres (EU region), free tier. Keep our own nightly `pg_dump` while on free tier (no backups included). Connect via the **session pooler** (IPv4; direct host is IPv6-only on free) |
| P4 | Auth | Supabase Auth, used by the frontend **only for login** (supabase-js). All data goes through FastAPI, which verifies the Supabase JWT against the project JWKS and takes `user_id` from it. Methods: email + password, Google. Apple later (needs paid Apple Developer account) |
| P5 | Supabase data API | App tables live in their own schema (e.g. `app`) not exposed via the Supabase Data API; RLS enabled with no policies on any exposed table as a second lock |
| P6 | Auth email | Custom SMTP (e.g. Resend free tier) from day one — Supabase's default sender is heavily rate-limited |
| P7 | Backend shape | One FastAPI app (modular monolith): `core/` (auth, db, config, crypto, timeutils) + `modules/<name>/` (router, models, service, tests) |
| P8 | Data isolation | L1: every endpoint takes `current_user`, every query goes through helpers that require `user_id`. L2: per-module cross-user isolation tests (user B gets 404 on read/update/delete of user A's rows). L3 (Postgres RLS) later — see TODO |
| P9 | Background jobs | Procrastinate (Postgres-backed queue, psycopg 3), separate `worker` container; periodic tasks for Strava sync, weekly quests, reminders |
| P10 | Secrets at rest | Per-user third-party secrets (Strava client secret, tokens) encrypted with Fernet; one master key in the server env (`ENCRYPTION_KEY`), backed up outside the DB; rotation via `MultiFernet` |
| P11 | Carry-over stack | Keep FastAPI, SQLModel, Alembic, psycopg 3, client-generated UUIDs + idempotent upserts, timeutils, React/Vite/TanStack Query PWA |
| P12 | Time zone | Per-user setting; default taken from the browser (`Intl.DateTimeFormat().resolvedOptions().timeZone`) at signup; replaces the global `APP_TZ` for day buckets |
| P13 | Strava | Bring-your-own Strava API app per user at first (client id/secret in settings, encrypted); in parallel request a higher athlete limit for our own app; FIT/GPX upload as a no-API fallback. Check the current Strava API Agreement (AI-use and data-display limits) before building |
| P14 | Languages | i18n-ready from day one (`react-i18next`, all UI strings in locale files); ship Czech only for now, add English later. AI reply language follows the prompt — Czech by default, later driven by the user's language setting |
| P15 | Code reuse | Copy modules/components from Fitness Hub into the new repo; no shared package. The two apps may drift apart. Personal-only features can later live behind per-user feature flags, so a full move to the new app stays possible |
| P16 | Logged-out pages | Login, sign-up, password reset, landing + privacy policy live inside the PWA (no separate website). Auth emails use 6-digit OTP codes typed into the app rather than links, so the installed PWA never gets bounced to Safari |

## TODO
- [ ] **L3 data isolation: Postgres row-level security** on all user-owned tables. Policies use our own
      `current_setting('app.user_id')` (set per transaction by FastAPI), not Supabase's `auth.uid()`, so they stay
      portable. The app's DB role must not own the tables or have `BYPASSRLS` (or use `FORCE ROW LEVEL SECURITY`).
- [ ] Back up `ENCRYPTION_KEY` outside the server (password manager) — losing it makes stored Strava secrets unreadable.
- [ ] Read the current Strava API Agreement before building the Strava module.
- [ ] GDPR basics (health data = Art. 9): consent, privacy policy, data export, account deletion.
- [ ] Per-user feature flags (e.g. `user_features` table + `is_admin`) for personal or beta-only modules.
- [ ] Test Google login in the installed iOS PWA early (OAuth redirects can escape to Safari in standalone mode).
- [ ] AI cost control: per-user quotas; later paid tier or bring-your-own Gemini key.

## Open steps
- Step 7: AI (keys, quotas)
- Step 8: Ops (home-server exposure and isolation, backups, error tracking, domain, CI/CD)
