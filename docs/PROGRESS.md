# Progress

**Current phase:** Phases 0–3 code-complete. Phase 4 in progress: the prod stack is **live** on the real data (project `fitness-hub`, daily backups), and the dev stack is separate (`./dev`, E14).
**Next step:**
1. ✅ `tailscale serve` switched (2026-10-17): https://biggyserver.tailfff1d3.ts.net → prod 8010, `:8443` → dev Vite 5173. The iPhone's Tailscale was offline (last seen 2 days ago) at that point.
2. ✅ iPhone: PWA installed, voice works. Keep an eye on the GymLogger in real use.
3. Integrations: ✅ Strava, ✅ Health Connect. **TODO later:** the iOS Shortcut (the user will do it with guidance).
4. **Habits module ("Rutina") proposed** in `docs/habits-module-spec.md` (draft + mockup); waiting for the user's answers to H1–H4 before implementing.
5. Phase 5 done except deferred barcode scanning. The user starts the KT history import in Nastavení (prod). The user still has to put the KT credentials into `.env` before 5.5.
**Stacks:** prod `docker compose …` → http://127.0.0.1:8010 (`fitness-hub-app-1`, `-db-1`, `-backup-1`); dev `./dev …` → backend http://127.0.0.1:8020, Vite :5173. Ops guide: `docs/operations.md`.
**Git:** work happens on the `dev` branch. Commit after each verified step. `master` stays at the initial spec until merged. Never commit `.env` or `data/`.

## Decisions
| Id | Date | Decision |
|---|---|---|
| E0 | 2026-10-17 | Apply all core fixes A1–A13 from the review. Docs are split into CLAUDE.md / docs/SPEC.md / docs/PROGRESS.md. |
| E1 | 2026-10-17 | Intake lives only in `meal_logs`/`meal_log_items`. `DailyMetric` has no calories_in or macros, and the dashboard's "kcal" input is a quick-add meal item. Minimal meal tables ship in Phase 1. |
| E2 | 2026-10-17 | **Two separate assistants** (coach, nutrition) on a shared Gemini runner, with separate prompts, toolsets and conversations. The coach only reads intake totals and has a quick-kcal tool. |
| E3 | 2026-10-17 | **USDA is bulk-seeded locally**: SR Legacy (7,793 foods) + Foundation (`foundation_food` rows only), from USDA's CSV editions (streamed; the SR JSON is 210 MB unzipped) with pinned URLs + sha256. Only mapped nutrients and portions are stored; search runs locally with `pg_trgm` on `name_en`. No USDA API key, no rate limits. |
| E4 | 2026-10-17 | Hybrid save flow for AI-parsed data: auto-save only on high-confidence or confirmed matches, otherwise a draft card for 1-tap confirmation. Aliases are learned only on confirmation. |
| E5 | 2026-10-17 | The Strong sticky notes mark different exercises. Remap `Lat Pulldown (Machine)` → Bent-over Pulldown and `Lat Pulldown - Underhand (Cable)` → Kelso Shrug for all workouts. **Confirmed by the user** (O1): all 40 underhand workouts are Kelso Shrugs, and the March 2026 low-rep sets stay the same movement. |
| E6 | 2026-10-17 | iPhone steps come via an iOS Shortcut → health webhook. Re-checked 2026-10-17: Life Dashboard Companion's iOS app speaks the same format and `/api/webhooks/health-connect` already accepts it, but it has no App Store or TestFlight build. It needs a Mac with Xcode 26 and a free account (re-sign every 7 days) or a paid one ($99/yr), so the Shortcut stays. Switching later needs no backend change. |
| E7 | 2026-10-17 | Steps merge: 15-min buckets, max per bucket, summed over the day. Fallback: max of the sources' daily totals. |
| E8 | 2026-10-17 | Samsung Health (watch steps, sleep) via live Health Connect sync. Forwarder app on the Android phone, chosen in Phase 1. |
| E9 | 2026-10-17 | Gym: auto-finish idle workouts (2 h) + "Start from last …" templates. The KT weight import stays in Phase 5. |
| E10 | 2026-10-17 | Strava via OAuth + polling (no public webhook). Strava is the only automatic activity source. |
| E11 | 2026-10-17 | The coach builds on the user's **RunningCoach** repo (github.com/PavelJanosekk/RunningCoach), which **stays the source of truth**. The app syncs it from GitHub daily and on demand. Rules, quick facts, zones and errata go into every coach request; other docs are read via a tool. The weekly plan tables, races and LTHR are parsed into the DB for the Run page. The user keeps their Claude Code "aktualizuj log" workflow there. |
| E12 | 2026-10-17 | Port RunningCoach `scripts/metrics.py`: per-run GAP (Minetti), EF, decoupling and time per LTHR zone from per-second Strava streams, plus RPE and description from the activity detail. Backfilled within Strava rate limits. Progress is judged at equal HR and GAP; heat runs are excluded from trends. |
| E13 | 2026-10-17 | O6: HTTPS via **`tailscale serve`**, not Caddy. Caddy's config stays untouched. |
| E15 | 2026-10-17 | **Free Gemini quota is split across models** (free tier = 20 requests/day *per model* on Flash). Coach stays on `GEMINI_MODEL_FAST` (gemini-3.7-flash), the nutrition assistant runs on `GEMINI_MODEL_NUTRITION` (gemini-3.6-flash), and one-shot helpers (food picker, estimates) run on `GEMINI_MODEL_LITE` (gemini-3.5-flash-lite). Empty = fast model. Search grounding is not in the free tier, so the estimate falls back to the model's own knowledge, flagged `grounded: false`. |
| E16 | 2026-10-17 | **KT history is imported 1:1.** The user's own KT recipes ("Recky protein" = yoghurt + protein, amounts changing daily) arrive as plain entries without ingredients, so imported items keep KT's exact per-day kcal/P/C/F (the one exception to C8). The food holds the newest composition for future logging; fibre and micros come from the food. Barcode scanning is deferred (user, 2026-10-17). |
| E17 | 2026-10-17 | **Run page redesign.** Volume chart on top (10 weeks, km vs plan). Current week = header + progress bar + list of its runs (done = check + greyed, Strava link, tap jumps to the run in "Poslední běhy"). "Plán po týdnech" = expandable tiles (no bars), 4 per page. Planned runs come from the day-by-day schedule lines in `04_timeline_plan.md` (code blocks under a dated heading, weekday must match the date) → `training_days` (migration 0009, replaced on every sync), paired with actual runs by date; weeks without a schedule fall back to long run + quality + easy remainder derived from the weekly table. `/api/running/weeks` now returns `days` and `runs` per week. Confirmed by the user. |
| E18 | 2026-10-17 | **Gym page rework.** Templates are now a hand-managed entity (`workout_templates`, migration 0010, seeded once from history: names done ≥3 times) with create/edit/delete in the UI; starting one pre-fills its kg × reps. Unfinished workouts can be discarded (server delete, queued in the gym scope). History is paged, rows open a read-only detail, PR badges are computed server-side (heaviest weight → else Epley 1RM → else reps for bodyweight; needs an earlier workout; warm-ups excluded). Template query key bumped to `v2` because the phone's persisted cache holds the old shape. Confirmed by the user. |
| E19 | 2026-10-18 | **Switchable themes** (user request): the current look stays as *Minimalistický* (default), plus *Moderní* (design left to the agent: midnight glass cards over a violet/cyan/pink aurora, violet gradient accent, SF Pro Rounded, floating pill tab bar) and *Zen* ("Japanese zen living room": washi paper beige, sumi ink, matcha/sage accent, earth-tone status colors, serif headings, faint ensō, hanko seal after page titles, a dark wooden band under the iOS status bar because `black-translucent` keeps its text white). Switcher in Nastavení → Vzhled, stored per device in localStorage (`fitness-hub-theme`), applied before first paint by an inline script in `index.html`. Mechanism: `<html data-theme>` remaps the Tailwind palette names the pages already use (zinc = neutral roles, emerald = accent, amber/red/sky/violet = status) plus `ui-*` component classes for shape; charts get one validated palette per theme. Sheets are portaled to `<body>` because glass cards (backdrop-filter) would trap `fixed` children. |
| E20 | 2026-10-18 | **Gemini model fallback** (user request: the coach failed once `gemini-3.7-flash` used its 20 free requests/day; every AFC tool round is one request). `GEMINI_MODEL_FALLBACKS` (comma-separated) is tried in order after the assistant's own model on 429 or 503, for both assistants. A turn that already ran a writing tool (`log_*`) is not re-run, so nothing is logged twice: the user gets the 429. Live check 2026-10-18: 3.7-flash and 3.5-flash exhausted, 2.5-flash retired (404), 3.8-flash answered with tools, 3.1-flash-lite answered (once 503 under load). |
| E14 | 2026-10-17 | **Separate dev stack.** Prod is compose project `fitness-hub` (existing DB volume with the real data, backups) and stays up on 8010. Dev is project `fitness-hub-dev` with its own DB seeded from the newest prod backup, the scheduler off, Strava tokens wiped, backend on 8020 and Vite on 5173. `./dev` wraps the dev compose command. tailscale serve: :443 → prod, :8443 → dev Vite. |

## User facts (answers F1–F5, 2026-10-17)
- **F1:** Strong export is in `data/imports/strong_workouts.csv`: 123 workouts, 2,361 sets, 42 exercises, 2025-08-07 → 2026-10-17. Analysed in review §G1.
- **F2:** iPhone 16 Pro (main phone, PWA) and Galaxy Watch 6 Classic (non-LTE, paired with an Android phone running Samsung Health). Strava records runs; Apple Health has phone steps and Samsung Health has watch steps.
- **F3:** KalorickéTabulky, non-Premium. Load through the `kaloricketabulky-sdk` Python package (tomasvotava). Analysed in review §G2.
- **F4:** Single user for now; might change later.
- **F5:** Commit as we go.

## Open items
| Id | Item | When |
|---|---|---|
| O3 | ✅ Verified on real days: grams = count × unit grams (`"2,5 x kus (50 g)"` = 125 g), nutrients per entry, Na/Ca in g, diary totals 0 (sum the items), ml ≈ g | Phase 5 |
| O4 | ✅ E3: bulk seed | Before Phase 5 |
| O5 | ✅ Live list checked: fast = `gemini-3.7-flash` (works with tool calls + typed args; served as 3.8-flash). **The key is on the free tier: Pro = 0 quota.** Smart tier = same Flash with high thinking until billing is enabled. Free-tier data may be used by Google; paid tier not. User: no paid calls for now | Phase 2 |
| O6 | ✅ `tailscale serve` (E13) | Phase 4 |
| O7 | Habits module decisions H1–H4 (`docs/habits-module-spec.md`) | Before the habits module |

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
- [x] 3.6 Settings: integrations + KB status/sync, Strong import; PWA manifest/icons; FastAPI serves built SPA (prep for Phase 4)

### Phase 4: Docker & deploy
- [x] Multi-stage Dockerfile (minimal static ffmpeg 8.1.3), compose (db, app, backup), healthchecks, SPA fallback; prod image smoke-tested on a fresh DB (363 MB, was 1.04 GB with Debian's ffmpeg)
- [x] Backups: daily `pg_dump`, 7/4/6 rotation, restore verified; `docs/operations.md`
- [x] E14 split: prod live on the existing volume, dev project with its own DB + `scripts/seed-dev-db.sh`, `./dev` wrapper; CLAUDE.md/SPEC commands updated
- [x] `tailscale serve` → :443 prod (8010), :8443 dev (5173); both answer over the tailnet
- [x] iPhone over Tailscale: PWA installed from Safari, voice dictation works (first real-device check of the mic). Tailscale also on the Windows PC.
- [x] Integration guides `docs/integrations/` (strava, ios-shortcut, health-connect); `.env` has `PUBLIC_BASE_URL` + a generated `WEBHOOK_TOKEN`; webhooks verified end to end on dev; `/api/webhooks/health` reads JSON whatever the Content-Type (Shortcuts)
- [x] Strava connected (2026-10-17): 301 activities 2021-05 → 2026-10 (165 runs); stream metrics backfill 10 runs per sync
- [x] Life Dashboard Companion on the Android phone (2026-10-17): Samsung Health steps arriving (16 days at first, 365-day backfill running); no sleep yet (watch not worn at night)
- [ ] **TODO (user, later):** iOS Shortcut for iPhone steps + automations (`docs/integrations/ios-shortcut.md`)

### Phase 5: Nutrition module
`docs/nutrition-module-spec.md` with its Amendments. E3 decided (bulk seed). Steps, each committed + pushed:
- [x] 5.1 Schema + migration 0007: `foods` (int PK, name_cs/name_en, category, required kcal/P/C/F, nullable sugar/sat-fat/fiber/salt, `micronutrients` JSONB with known keys only, micros reference, recipe yield, trigram indexes), `food_aliases` (+confirmed), `food_portions`, `recipe_components`, `nutrition_profile`; `meal_log_items` gains `food_id` + `amount_g` and `kcal` becomes nullable (manual quick-add only); intake totals computed live through `foods` (metrics + `/day`); `nutrients.py` (keys, units, Czech labels, RDI)
- [x] 5.2 USDA seed (CSV, pinned, idempotent; runs on start when missing) + Open Food Facts client (barcode, search) with fixture tests
- [x] 5.3 Resolver (alias → local foods → USDA candidates → Gemini pick; hybrid save, aliases on confirmation) + tests
- [x] 5.4a Routes without AI: `/summary` (every nutrient with coverage + profile/EU target, training-day kcal), food items PUT (client UUID), foods search/CRUD (delete guarded), `/barcode/{ean}` (local → OFF), `/profile`, `/drafts/confirm` (idempotent, learns aliases)
- [x] 5.4b Nutrition assistant: prompt (known foods C7, portions), tools `log_meal_from_items` + `get_daily_nutrition_summary`, Gemini chooser + web estimate, `/chat` + `/voice`
- [x] 5.5 KT importer: `kaloricketabulky-sdk==0.1.1` (+ `env-proxy==1.7.0`; reviewed, >14 days), migration 0008 (`meal_logs.source`, `kt_import_state`), throttled resumable background job (auto-resumes after restart), weights fill empty days, days logged in the app skipped; Settings card. Dev run matched KT 1:1
- [x] 5.6a Frontend: "Jídlo" tab (5th nav item; day switcher, kcal/macro bars vs targets, assistant text + voice with meal draft cards, meals with inline grams + delete, manual add from the food DB, micros grid dimmed under 70 % coverage, targets sheet) + `/nutrition/foods` database page (search, source filter, edit/create/delete)
- [ ] 5.6b Barcode scanning: **deferred by the user** (needs `@zxing/browser` for iOS Safari)

## Backlog (ideas, not accepted)
- D1 `Exercise.secondary_muscles` for better volume analysis
- D2 Race goal + AI-generated marathon plan; auto-link activities to plan items
- D3 Progressive-overload suggestion alongside ghost values
- Adaptive TDEE from weight trend + intake (AI coach tool)
- NutriDatabáze.cz as a Czech food source (licensing unverified)
- KT weight history import earlier than Phase 5 (declined for now in E9)
- Switch iPhone steps from the iOS Shortcut to the Life Dashboard Companion iOS app once it reaches TestFlight or the App Store (receiver already supports `healthkit_ios`)
- D4 Frontend test runner (vitest) with the offline-sync cases from the 2026-10-17 harness (outage, 502, 4xx, reopen mid-retry)

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
- **2026-10-17 (14):** 3.6 Settings page (Strava connect/sync, webhook sources, KB status/sync, Strong import, pending changes), route code-splitting (core 305 kB, Dashboard + recharts 384 kB), FastAPI `mount_spa` (`STATIC_DIR`, no-cache index/sw, API 404s win, traversal-safe, 129 tests), and a Dockerfile frontend build stage.
  - **The prod image has not been built or tested yet.**
  - Session ended at the usage limit.
- **2026-10-17 (15):** Phase 4, part 1.
  - Slim image: ffmpeg 8.1.3 built from a GPG-verified, sha256-pinned tarball with only the audio parts the voice path uses (2.9 MB binary). Dev image 1.04 GB → 418 MB, prod 363 MB. The voice test uses committed 1 s fixtures (Chrome webm/Opus, Safari fragmented mp4/AAC).
  - Prod image smoke-tested as a throwaway project on an empty DB: migrations 0001–0006, seed, SPA deep links, PWA files, no-cache/immutable headers, traversal, ffmpeg as uid 10001.
  - Backup service + `docs/operations.md`. Rotation tested with fake old dumps; restore (also `--clean` over an existing DB) matches a real-data copy exactly.
  - Decisions E13 (tailscale serve) and E14 (separate dev stack). Prod now runs on the existing volume, and a safety dump `data/backups/manual-pre-split-2026-10-17.dump` was taken before the switch. Dev was seeded from the first prod backup; the leftover `fitness_db_test` was dropped from prod.
  - The user was logging a workout ("Chest tri") on the phone through `tailscale serve` → :5173 when the old dev Vite container was removed, about 3 minutes of downtime. `tailscale serve` can't be changed without sudo, so as a stopgap prod is published on host port 5173 (`APP_PORT=5173 docker compose up -d app`); :443 already points there. The user's switch, from the repo root:
    `sudo tailscale serve reset && sudo tailscale serve --bg 8010 && sudo tailscale serve --bg --https=8443 5173 && docker compose up -d app && ./dev up -d`
  - Slip: one `docker compose config` printout showed the resolved Postgres password in the session log (nowhere else). Since then only key presence is checked, never values.
  - Integrations: guides for Strava, the iOS Shortcut and Health Connect. Set `PUBLIC_BASE_URL` and a random `WEBHOOK_TOKEN` in `.env` (values never printed). Prod rejects wrong tokens (401); full pushes tested on dev (Shortcut payload shape, the documented Life Dashboard ping).
    - The Shortcut design accounts for iOS locking Health data while the phone is locked: a guard (0 samples → stop) protects the replace-per-day rule, and an "app opened" trigger runs while the phone is in use.
    - `/api/webhooks/health` now parses the raw body (Shortcuts may label JSON as octet-stream). Both webhooks drop pydantic's `ctx` from 422 details: a validator's ValueError there made the old 422 path crash with a 500 (132 tests).
  - **Gym sync data-loss bug fixed** (found while checking the outage's effect): with the server unreachable but the phone online, a set PUT gave up after ~30 s, TanStack persisted only paused mutations, and `finish()` cleared the local workout, so the set was gone. Now gym writes retry while the server is unreachable (network/408/429/502–504, backoff capped at 30 s), in-flight writes are persisted and resumed on reopen, and finish re-sends all completed sets. Checked with a throwaway harness on the real `gym.ts` (scratchpad, not committed: no frontend test runner yet). Deployed to prod.
  - At the end of the session: the "Chest tri" workout is open on the server with 0 synced sets. If sets were completed during the outage, they come back when the user taps **Dokončit** in the reloaded app; otherwise auto-finish closes it after 2 h.
- **2026-10-17 (16):** The tailnet URL failed at first because neither the iPhone nor the PC was connected to Tailscale: outside the tailnet the ts.net name resolves to Tailscale's public servers, which close the connection. With Tailscale on both, the PWA is installed and voice works on the iPhone. The user deleted the empty "Chest tri" workout, which came from the server's localhost, not the phone. Strava connect gave `redirect_uri invalid`: the app sends the right callback, and Strava accepts the client id with localhost, so the Strava app's *Authorization Callback Domain* has to be set to `biggyserver.tailfff1d3.ts.net`; the user is fixing that.
- **2026-10-17 (17):** Strava connected once the callback domain was fixed. The first sync brought 301 activities (165 runs, 106 rides, 22 swims, 2021-05 → 2026-10) and stream metrics for the 10 newest runs; 105 runs with HR remain, 10 per 30-min sync (~5–6 h). **E12 checked on real data:** decoupling matches the RunningCoach log exactly (LR 13.9. +6.2 %, LR 20.9. −2.4 %, 6.10. 7.9 %). Extreme values on short easy runs (23.9. −33 %, 15.10. −18 %) come from fast or downhill starts while HR lags, as the log itself describes.
- **2026-10-17 (18):** Life Dashboard Companion installed (1.26.0) with the token header. 125 payloads accepted; daily steps for 18.9.→today; the 365-day backfill is running. The user deferred the iOS Shortcut; next up is Phase 5.
- **2026-10-17 (19):** E3 decided: bulk seed from USDA's CSV editions. 5.1: models + migration 0007 (round-trip tested; trigram indexes are hand-written and excluded from autogenerate via `include_object`); `services/nutrition/` is now a package with `nutrients.py` (USDA id fallback chains, sums, salt from sodium, EU NRV references); intake totals computed live through `foods` in `/day` and `intake_by_day` (139 tests).
- **2026-10-17 (20):** 5.2: USDA seed from the CSV editions (8,170 foods + 14,612 portions in 12 s on dev; 92 skipped without a required macro; real data has negative carbs-by-difference, now clamped to 0; the startup seed never blocks the app). Spot checks match USDA (rice 130 kcal, banana 89, egg 143). US portion sizes differ from Czech ones (US medium egg 44 g vs Czech "vejce M" 55 g), so Czech portions/aliases must take precedence in the resolver. OFF client: barcode lookup + search.openfoodfacts.org (noisy, so Gemini picks), kJ fallback, upsert by EAN; response shapes recorded from live calls (150 tests).
- **2026-10-17 (21):** 5.2 deployed to prod (backup `manual-pre-0007-…dump` first; 0007 migrated, 8,170 USDA foods seeded). 5.3 resolver: confirmed = confirmed alias, a known food already eaten, or an exact Czech name on a user/KT food; otherwise candidates (local by Czech name, OFF for branded, USDA by a trigram + full-text pool re-ranked by query-word coverage with a head-word bonus and same-name dedupe), a Chooser picks (Gemini in 5.4), web estimate when nothing is found. Aliases and a USDA food's Czech name are written only on confirmation. Search checked on 18 typical queries against the real seed (161 tests).
- **2026-10-17 (22):** 5.4a: summary, items, foods, barcode, profile and draft-confirm routes. A test caught a KeyError when a quick-add item met the micronutrient summary (fixed) (168 tests).
- **2026-10-17 (23):** 5.4b: nutrition assistant (Czech prompt with the 150 most-eaten foods + typical portions, local time; tools `log_meal_from_items` and `get_daily_nutrition_summary`), GeminiChooser (one structured call per meal, falls back to top score on any error), web estimate as a separate Google-Search-grounded call, `/api/nutrition/chat` + `/voice`. Shared `services/conversations.py`, `run_gemini` and `audio_part`; the Gemini fake moved to `tests/fakes.py` (180 tests).
- **2026-10-17 (24):** Live check. The first attempt hit the daily free quota: **20 requests/day per model** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), so the user chose E15 (split models).
  - Live on dev with gemini-3.6-flash + gemini-3.5-flash-lite. The first turn failed because the SDK's AFC argument conversion can't `isinstance`-check a top-level `Literal` parameter (`meal_type`); it's now a plain str validated in the tool, with a test that drives the tools through the SDK's own conversion.
  - The spec example "200g kuřecích stehen bez kůže na lžíci sádla a 300g vařených brambor" gave the correct canonical names and grams, and Flash-Lite picked the right USDA foods (conf 0.95–0.99; it rejected "Potatoes … in skin, skin", the top keyword hit).
  - Confirm learned the aliases. A repeat meal auto-saved with 2 requests (no picker). The summary question answered correctly with coverage.
  - Google Search grounding returns 429 on the free tier, hence the ungrounded fallback. The prompt now asks for `user_phrase` without the amount. 183 tests. Backend deployed to prod.
- **2026-10-17 (25):** 5.6a frontend. Headless screenshots now work (zenika/alpine-chrome:124 with `--virtual-time-budget=30000` against the dev Vite server); they led to two fixes: food names wrap instead of truncating, and the food list without a query shows the user's foods instead of 8k USDA rows (185 tests). Deployed to prod.
- **2026-10-17 (26):** 5.5 KT import.
  - The SDK was reviewed before installing it: read-only, talks only to kaloricketabulky.cz; `kaloricketabulky.config` loads `.env` on import, so only `kaloricketabulky.sdk` is imported. It and `env-proxy` were added to the existing freeze; installed set == constraints.
  - O3 verified on real days (see Open items).
  - The first dev import didn't match KT (1,711 vs 1,780 kcal): the user's own recipes change composition daily and expose no ingredients, hence E16 (exact per-day values on imported items). A re-run matches KT exactly on 16.10. (1,780.4 kcal, P 179.0, C 95.5, F 71.8).
  - A test caught a rounding bug (sodium/calcium rounded in g before the mg conversion). 203 tests.
- **2026-10-18:** Gym: drag-and-drop reordering of exercises (grip handle) in the template editor and the active workout, replacing the up/down arrows. Own pointer-events hook `lib/useDragReorder.ts` (no new dependency) with edge auto-scroll; reordering an active workout re-sends the completed sets whose `exercise_order` changed. Verified with a scripted drag in headless Chrome.
- **2026-10-18 (2):** Gym: compact Strong-style set tables in the active workout and the template editor (`components/gym/SetTable.tsx`): one 36px row per set (set | last time | kg | reps | ✓), the ± steppers dropped. Tapping "Minule" copies last session's values; tapping the set number changes the set type (W/D/F) or deletes the set; the header shows done/total sets. The template list shows the exercise names. Tapping a kg/reps input selects its value, so typing replaces it.
- **2026-10-18 (3):** E19 themes. Chart palettes for modern (dark, surface ~#151729) and zen (light, paper #fbf8f1) pass every dataviz validator check; zen text colors checked for WCAG contrast (secondary text 5.7:1, accent fill with paper text 4.9:1, white on the modern accent 4.5:1). Verified with headless-Chrome screenshots of every page in all three themes (dashboard, gym start + active workout with rest timer, run, nutrition, coach, a sheet, settings); minimal looks as before. Fonts in headless Alpine fall back, so the rounded / serif faces are only visible on Apple devices. The weight chart now uses whole-kg ticks (half-kg ticks printed as 83, 83, 82, 82). Both deployed to prod.
- **2026-10-18 (4):** Gym: exercise management. "Cviky" in the Gym header opens `/gym/exercises` (search, muscle-group filter, create, edit name / group / equipment); the exercise picker can create the searched exercise and adds it straight to the workout or template. Uses the existing `POST`/`PATCH /api/exercises`, now with stripped names and case-insensitive uniqueness (409). A rename also updates the workout in progress. Online only (the server assigns the id). No delete yet. Checked by a scripted headless-Chrome run on dev (create, rename, duplicate error, create from the picker); test rows removed from the dev DB (209 tests).
- **2026-10-18 (5):** KT import defaults to yesterday and no longer skips days with app-logged meals (KT's meals are added next to them, double-count warning; re-imports replace only KT's). Nutrition assistant: chat and voice now send the day open in the Jídlo tab (`date`), used as the default for `log_meal_from_items` / the summary and named in the prompt; an explicit day in the user's words still wins. Replaces the `[den …]` text prefix, which voice never had (212 tests).
- **2026-10-18 (6):** User asked for a daily/weekly habit tracker (their Google Sheet) with charts, and an RPG layer later (streaks, XP, skills). Reviewed their Gemini-written addendum (12 findings: non-idempotent toggle, no unique day, undefined streak edges, no start/archive dates, no edit/order, points/bonus missing, etc.) and wrote `docs/habits-module-spec.md` (draft) plus a 5-screen mockup canvas. Decisions H1–H4 pending (O7).
