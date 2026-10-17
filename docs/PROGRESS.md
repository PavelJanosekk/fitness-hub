# Progress

**Current phase:** Phases 0–2 done and verified (backend + AI coach, 122 tests, live free-tier check passed). Phase 3 (React frontend & PWA) not started.
**Next step:** Phase 3, step 3.6 Settings page, FastAPI serving the built SPA, route code-splitting. GymLogger still needs a check in a real phone browser (no visual check yet). Dev UI: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` → http://127.0.0.1:5173. Each step is committed and pushed to `origin/dev` as soon as it's verified.
**Dev stack:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build` serves http://127.0.0.1:8010 (containers `fitness-hub-app-1`, `fitness-hub-db-1`).
**Git:** work happens on the `dev` branch. Commit after each verified step. `master` stays at the initial spec until merged. Never commit `.env` or `data/`.

## Decisions
| Id | Date | Decision |
|---|---|---|
| E0 | 2026-10-17 | Apply all core fixes A1–A13 from the review. Docs are split into CLAUDE.md / docs/SPEC.md / docs/PROGRESS.md. |
| E1 | 2026-10-17 | Intake lives only in `meal_logs`/`meal_log_items`. `DailyMetric` has no calories_in or macros, and the dashboard's "kcal" input is a quick-add meal item. Minimal meal tables ship in Phase 1. |
| E2 | 2026-10-17 | **Two separate assistants** (coach, nutrition) on a shared Gemini runner, with separate prompts, toolsets and conversations. The coach only reads intake totals and has a quick-kcal tool. |
| E3 | — | *Pending, decide before Phase 5:* bulk-seed USDA locally (recommended) vs. lazy API lookup. |
| E4 | 2026-10-17 | Hybrid save flow for AI-parsed data: auto-save only on high-confidence or confirmed matches, otherwise a draft card for 1-tap confirmation. Aliases are learned only on confirmation. |
| E5 | 2026-10-17 | The Strong sticky notes mark different exercises. Remap `Lat Pulldown (Machine)` → Bent-over Pulldown and `Lat Pulldown - Underhand (Cable)` → Kelso Shrug for all workouts. **Confirmed by the user** (O1): all 40 underhand workouts are Kelso Shrugs, and the March 2026 low-rep sets stay the same movement. |
| E6 | 2026-10-17 | iPhone steps come via an iOS Shortcut → health webhook. Re-checked 2026-10-17: Life Dashboard Companion's iOS app speaks the same format and `/api/webhooks/health-connect` already accepts it, but it has no App Store or TestFlight build. It needs a Mac with Xcode 26 and a free account (re-sign every 7 days) or a paid one ($99/yr), so the Shortcut stays. Switching later needs no backend change. |
| E7 | 2026-10-17 | Steps merge: 15-min buckets, max per bucket, summed over the day. Fallback: max of the sources' daily totals. |
| E8 | 2026-10-17 | Samsung Health (watch steps, sleep) via live Health Connect sync. Forwarder app on the Android phone, chosen in Phase 1. |
| E9 | 2026-10-17 | Gym: auto-finish idle workouts (2 h) + "Start from last …" templates. The KT weight import stays in Phase 5. |
| E10 | 2026-10-17 | Strava via OAuth + polling (no public webhook). Strava is the only automatic activity source. |
| E11 | 2026-10-17 | The coach builds on the user's **RunningCoach** repo (github.com/PavelJanosekk/RunningCoach), which **stays the source of truth**. The app syncs it from GitHub daily and on demand. Rules, quick facts, zones and errata go into every coach request; other docs are read via a tool. The weekly plan tables, races and LTHR are parsed into the DB for the Run page. The user keeps their Claude Code "aktualizuj log" workflow there. |
| E12 | 2026-10-17 | Port RunningCoach `scripts/metrics.py`: per-run GAP (Minetti), EF, decoupling and time per LTHR zone from per-second Strava streams, plus RPE and description from the activity detail. Backfilled within Strava rate limits. Progress is judged at equal HR and GAP; heat runs are excluded from trends. |

## User facts (answers F1–F5, 2026-10-17)
- **F1:** Strong export is in `data/imports/strong_workouts.csv`: 123 workouts, 2,361 sets, 42 exercises, 2025-08-07 → 2026-10-17. Analysed in review §G1.
- **F2:** iPhone 16 Pro (main phone, PWA) and Galaxy Watch 6 Classic (non-LTE, paired with an Android phone running Samsung Health). Strava records runs; Apple Health has phone steps and Samsung Health has watch steps.
- **F3:** KalorickéTabulky, non-Premium. Load through the `kaloricketabulky-sdk` Python package (tomasvotava). Analysed in review §G2.
- **F4:** Single user for now; might change later.
- **F5:** Commit as we go.

## Open items
| Id | Item | When |
|---|---|---|
| O3 | KT `unit` grams: per entry or per unit? Are nutrient values per entry? Verify on one real diary day | Phase 5 |
| O4 | E3: USDA bulk seed vs. lazy API | Before Phase 5 |
| O5 | ✅ Live list checked: fast = `gemini-3.7-flash` (works with tool calls + typed args; served as 3.8-flash). **The key is on the free tier: Pro = 0 quota.** Smart tier = same Flash with high thinking until billing is enabled. Free-tier data may be used by Google; paid tier not. User: no paid calls for now | Phase 2 |
| O6 | HTTPS: Caddy is already running on the server. Serve the app through it (with a Tailscale cert) or through `tailscale serve`? | Phase 4 |

## Phase checklist

### Phase 0: Scaffolding & dev loop
- [x] Backend skeleton: `config.py`, `database.py`, `timeutils.py`, `main.py` + `/api/health`, pinned requirements
- [x] Alembic + initial migration `0001` (`pg_trgm`, `unaccent`, `f_unaccent()`)
- [x] `Dockerfile` (dev/prod), `docker-compose.yml` (db + app on 127.0.0.1:${APP_PORT:-8010}), `docker-compose.dev.yml` (backend reload; Vite comes in Phase 3)
- [x] `.env.example`; pytest (test DB + rollback fixtures) + ruff (incl. DTZ); full dependency freeze in `constraints.txt` (all releases at least 14 days old)
- [x] Verified: dev stack healthy, `/api/health` ok, 13 tests pass with no warnings, ruff clean; prod image smoke-tested (non-root uid 10001, migrations on start, health ok)

### Phase 1: Backend core & database
- [x] Models (§5): DailyMetric, Exercise, Workout, WorkoutSet (+ `exercise_order`), Activity, TrainingPlanItem, MealLog/MealLogItem (minimal), ChatConversation/ChatMessage, StepBucket, DailySourceMetric, IntegrationToken + migration `0002`
- [x] Idempotent exercise seed: 58 exercises (all 42 from the Strong export, 2 remap targets, extras), run on container start
- [x] Routers: metrics, nutrition quick-add, workouts (last-performance, active, templates, UUID upserts), running (steps breakdown comes with the health webhook)
- [x] Strong CSV importer (NBSP/over-4 h durations, local tz, remap rules, lbs, `;` exports) + real import into the dev DB: 123 workouts, 2,361 sets, 0 new exercises, 76 estimated durations; re-import skips all 123
- [x] Health webhook `POST /api/webhooks/health` (X-Webhook-Token, replace-per-day) + `health_ingest.py` (15-min buckets, max per bucket summed, daily-max fallback, manual wins; sleep by wake-up day, overlaps counted once, Samsung > Apple) + `GET /api/metrics/steps-breakdown`
- [x] Strava OAuth (connect/callback with CSRF state) + incremental sync (7-day overlap, cursor only advances on complete syncs, calories via detail for runs ≤14 days, max 20/sync) + `/api/integrations/status`; `scheduler.py` asyncio loops (auto-finish every 10 min, Strava every 30 min); migration `0003` (health_source_status)
- [x] O2: Health Connect forwarder = **Life Dashboard Companion** (MIT, per-record steps + sleep, custom header/HMAC, offline outbox, 365-day backfill). Receiver `POST /api/webhooks/health-connect` (records by uuid, deletions, per-day rebuild, origin allowlist, sequence-ordered daily totals) + migration `0004`
- [x] Tests: 88 passing (upserts, last-performance, templates, auto-finish, metrics/intake, Strong import, step merge, sleep, Health Connect receiver, Strava with a fake API, auth)

### Phase 2: Gemini service & coach tools
- [x] O5: live model list; fast = smart = `gemini-3.7-flash` (free tier, no Pro quota), thinking LOW/HIGH; written to `.env`
- [x] `gemini_service.py` (chat API + AFC, tool calls from chat history), `coach.py`, `ai_tools.py` (10 tools, hybrid drafts), `routers/ai_coach.py` (chat, voice with ffmpeg→FLAC, conversations), `services/audio.py`
- [x] E11: RunningCoach KB sync every 6 h + on demand, parsing into training_weeks, races and athlete_profile; core docs in every prompt; `read_knowledge_base`; `/api/coach/kb*`; `/api/running/weeks`
- [x] E12: stream metrics (port of metrics.py), streams stored, budgeted backfill, recompute on LTHR change, `get_efficiency_trend`
- [x] Live check (free tier, 3 turns): progression from the real Strong data, races and plan from the KB, dictation "kelso šrag" → exact Kelso Shrug saved. Found and fixed: tool calls weren't captured in chat mode. The test workout was deleted afterwards.

### Phase 3: Frontend & PWA. Mobile-first: the user is mostly on the iPhone
Work in small steps; after each step **commit + push + tick here** (the user asked that nothing gets lost).
- [x] 3.1 Scaffold `frontend/` (Vite, React, TS, Tailwind v4, react-router, TanStack Query + persist, lucide, recharts, vite-plugin-pwa); `frontend` service in `docker-compose.dev.yml` (node:22, Vite :5173, `/api` → app:8000); `npm run build` + `tsc` pass
- [x] 3.2 Layout (bottom nav on phone, sidebar on desktop, safe-area insets), API client, Dashboard (weight + kcal quick input, weight 7d chart + kcal bars, steps/sleep tile)
- [x] 3.3 GymLogger: start from template / empty, active workout with ghost values, ±steppers, 1-tap complete + RestTimer, client UUIDs + persisted offline mutation queue, finish
- [x] 3.4 Run page: races countdown, plan vs actual weeks, activities with stream metrics
- [x] 3.5 AI Coach: chat, tier toggle, quick prompts, VoiceRecorder (MediaRecorder), DraftCard confirm
- [ ] 3.6 Settings: integrations + KB status/sync, Strong import; PWA manifest/icons; FastAPI serves built SPA (prep for Phase 4)

### Phase 4: Docker & deploy
- [ ] Multi-stage Dockerfile (ffmpeg), compose (db, app, backup), healthcheck, SPA fallback
- [ ] `tailscale serve`; verify mic + PWA install on the iPhone
- [ ] Integrations: Strava app + connect, iOS Shortcut, Health Connect forwarder; guides in `docs/integrations/`; data visible on the Settings page

### Phase 5: Nutrition module
- [ ] Decide E3, verify O3, then steps 1–6 of `docs/nutrition-module-spec.md` with its Amendments (KT via SDK)

## Backlog (ideas, not accepted)
- D1 `Exercise.secondary_muscles` for better volume analysis
- D2 Race goal + AI-generated marathon plan; auto-link activities to plan items
- D3 Progressive-overload suggestion alongside ghost values
- Adaptive TDEE from weight trend + intake (AI coach tool)
- NutriDatabáze.cz as a Czech food source (licensing unverified)
- KT weight history import earlier than Phase 5 (declined for now in E9)
- Switch iPhone steps from the iOS Shortcut to the Life Dashboard Companion iOS app once it reaches TestFlight or the App Store (receiver already supports `healthkit_ios`)

## Session log
- **2026-10-17 (1):** Reviewed the original spec and the user's nutrition spec; live-checked the USDA FDC and Open Food Facts APIs. Saved the nutrition spec and the review, got decisions E0/E1/E2/E4, and restructured the docs. Commit `959fa75` on `dev`.
- **2026-10-17 (2):** Got the F1–F5 answers.
  - Profiled the real Strong export: forgotten-finish durations, an NBSP thousands separator, sticky notes marking other exercises, kg units, empty RPE.
  - Reviewed the KT SDK (tomasvotava).
  - Designed device ingestion: Strava polling, iOS Shortcut, Health Connect forwarder, 15-min step merge.
  - Got decisions E5–E10 and updated SPEC, the nutrition amendments and the review §G.
- **2026-10-17 (3):** O1 confirmed (Kelso Shrug for all underhand workouts; March 2026 sets are the same movement). Started Phase 0 and wrote all scaffolding files.
  - Port 8000 is taken on the host by an unrelated service, so the app moved to `APP_PORT` (8010) and is bound to localhost.
  - Decided: no CORS; the Vite dev service waits for Phase 3.
  - Verification is blocked: no Docker access (not in the `docker` group) and no python3-venv.
- **2026-10-17 (4):** User joined the `docker` group. Phase 0 verified and committed.
  - Port 8000 turned out to be Portainer.
  - Capped 9 fresh transitive deps (e.g. starlette 1.8.0 → 1.7.0, SQLAlchemy 2.0.55 → 2.0.54, pydantic 2.14.1 → 2.13.5) and moved the full freeze into Phase 0.
  - Switched the test client to httpx2 and silenced Alembic's path_separator warning.
  - Noticed Caddy running on the server: when Phase 4 comes, ask whether HTTPS should go through it instead of `tailscale serve`.
- **2026-10-17 (5):** Phase 1 completed and committed in steps (6375663, 0bf91cb, 2a0a9ce, 7facb33, + Health Connect).
  - Real Strong history is imported into the dev DB.
  - Spec deviations recorded in SPEC: `exercise_order` column, float step buckets, the remap rule format, asyncio jobs instead of APScheduler, and the `health_source_status` / `health_records` tables.
  - O2 resolved: Life Dashboard Companion, with its own receiver endpoint.
  - Its iOS app could replace the iOS Shortcut (E6). Mentioned to the user as an option; no decision yet.
- **2026-10-17 (6):** Phase 2 started.
  - Checked the live Gemini models (free tier only; the user forbids paid calls) and added google-genai 2.28.0 (websockets capped at 16.1.1, google-auth at 2.59.1, pycparser at 3.0).
  - iOS companion app researched: no App Store or TestFlight build, so the Shortcut stays.
  - Read the user's RunningCoach KB.
  - Decisions E11/E12. Facts from the KB: LTHR 172, races 3.4. (half marathon) and 2.5.2027 (marathon), the watch is not worn at night, a Strava API app already exists.
- **2026-10-17 (7):** Phase 2 completed.
  - Commits: b83fe1b (coach core), c36dce9 (KB sync), b300e4c (stream metrics), plus the AFC history fix.
  - The KB synced live: 14 docs, 25 plan weeks, LTHR 172, both races.
  - `.env` now has GEMINI_MODEL_FAST/SMART and COACH_KB_REPO.
  - Stream metrics aren't tried on real data yet, because Strava isn't connected (Phase 4; the user's RunningCoach Strava API app can be reused).
  - Dev image is 1.04 GB due to ffmpeg; slim it in Phase 4.
- **2026-10-17 (8):** Pushed Phase 2 to origin/dev (6a6ffa1). Phase 3 started with a step plan; the user is close to the usage cap, so commit + push after every step.
- **2026-10-17 (9):** 3.1 scaffold.
  - Versions: React 19.3, Vite 8.3.2, TypeScript 7.0.2, Tailwind 4.3.3, react-router 8.4, TanStack Query 5.104.1 (persisted to localStorage, offlineFirst mutations), vite-plugin-pwa 1.3.0. Installed with `npm install --before=2026-10-03T10:00:00Z` (14-day rule).
  - Icons are generated with pure Python.
  - Frontend dev service is on :5173 with the `/api` proxy verified.
- **2026-10-17 (10):** 3.2 Dashboard: quick weight/kcal(+protein) entry, steps tile with a breakdown sheet, sleep, weight + kcal charts, weekly gym sets per muscle group and weekly run km.
  - Chart colors are the dataviz dark palette, validated against the card surface #111113.
  - The spec's weight + kcal combo chart would need two y-axes (a chart anti-pattern), so it is two stacked charts instead.
  - New backend endpoint `/api/metrics/weekly`. The bundle is 692 kB (recharts); code-split routes in 3.6.
- **2026-10-17 (11):** 3.3 GymLogger.
  - Local-first active workout in localStorage; only completed sets sync, as idempotent PUT/DELETE through persisted TanStack mutations; `registerGymMutations` with one shared scope keeps them in order.
  - Templates pre-fill sets from the last session (ghost values); two-line set rows with big steppers; rest timer stored as an end time; resume of a server-side open workout; the auto-finish on the server clears the local workout.
- **2026-10-17 (12):** 3.4 Run page: race countdowns, this week vs plan, the weekly plan list with progress, LTHR zones, runs with stream-metric chips. `/api/running/activities` now returns metrics, RPE and the heat flag (124 tests). Headless-Chromium screenshots hung (chromedp image), so the visual check is left to the user's phone.
- **2026-10-17 (13):** 3.5 AI Coach.
  - Chat with the Rychlý/Hloubkový tier, quick prompts, the conversation id kept in localStorage, a minimal Markdown renderer (no HTML).
  - VoiceRecorder (tap to record, webm or mp4 depending on the phone; needs HTTPS) on the coach page and as a floating mic in the active workout; AI-saved sets are merged into the local workout.
  - DraftCard confirms through the new `POST /api/ai/drafts/confirm` (shared `save_sets`, 125 tests).
