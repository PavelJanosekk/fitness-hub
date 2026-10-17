# Progress

**Current phase:** Phase 1 (backend core & database), not started. Phase 0 is done and verified.
**Next step:** Phase 1 models + migration `0002`, then the exercise seed, routers and Strong import (see the checklist below).
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
| E6 | 2026-10-17 | iPhone steps come via an iOS Shortcut → health webhook. |
| E7 | 2026-10-17 | Steps merge: 15-min buckets, max per bucket, summed over the day. Fallback: max of the sources' daily totals. |
| E8 | 2026-10-17 | Samsung Health (watch steps, sleep) via live Health Connect sync. Forwarder app on the Android phone, chosen in Phase 1. |
| E9 | 2026-10-17 | Gym: auto-finish idle workouts (2 h) + "Start from last …" templates. The KT weight import stays in Phase 5. |
| E10 | 2026-10-17 | Strava via OAuth + polling (no public webhook). Strava is the only automatic activity source. |

## User facts (answers F1–F5, 2026-10-17)
- **F1:** Strong export is in `data/imports/strong_workouts.csv`: 123 workouts, 2,361 sets, 42 exercises, 2025-08-07 → 2026-10-17. Analysed in review §G1.
- **F2:** iPhone 16 Pro (main phone, PWA) and Galaxy Watch 6 Classic (non-LTE, paired with an Android phone running Samsung Health). Strava records runs; Apple Health has phone steps and Samsung Health has watch steps.
- **F3:** KalorickéTabulky, non-Premium. Load through the `kaloricketabulky-sdk` Python package (tomasvotava). Analysed in review §G2.
- **F4:** Single user for now; might change later.
- **F5:** Commit as we go.

## Open items
| Id | Item | When |
|---|---|---|
| O2 | Choose the Health Connect forwarder app (Android phone, background push to a custom URL with a header, over Tailscale) | Phase 1 |
| O3 | KT `unit` grams: per entry or per unit? Are nutrient values per entry? Verify on one real diary day | Phase 5 |
| O4 | E3: USDA bulk seed vs. lazy API | Before Phase 5 |
| O5 | Check the current Gemini model ids against the live model list | Phase 2 |
| O6 | HTTPS: Caddy is already running on the server. Serve the app through it (with a Tailscale cert) or through `tailscale serve`? | Phase 4 |

## Phase checklist

### Phase 0: Scaffolding & dev loop
- [x] Backend skeleton: `config.py`, `database.py`, `timeutils.py`, `main.py` + `/api/health`, pinned requirements
- [x] Alembic + initial migration `0001` (`pg_trgm`, `unaccent`, `f_unaccent()`)
- [x] `Dockerfile` (dev/prod), `docker-compose.yml` (db + app on 127.0.0.1:${APP_PORT:-8010}), `docker-compose.dev.yml` (backend reload; Vite comes in Phase 3)
- [x] `.env.example`; pytest (test DB + rollback fixtures) + ruff (incl. DTZ); full dependency freeze in `constraints.txt` (all releases at least 14 days old)
- [x] Verified: dev stack healthy, `/api/health` ok, 13 tests pass with no warnings, ruff clean; prod image smoke-tested (non-root uid 10001, migrations on start, health ok)

### Phase 1: Backend core & database
- [ ] Models (§5): DailyMetric, Exercise, Workout, WorkoutSet, Activity, TrainingPlanItem, MealLog/MealLogItem (minimal), ChatConversation/ChatMessage, StepBucket, DailySourceMetric, IntegrationToken + migration
- [ ] Idempotent exercise seed (all 42 exercises from the Strong export + extras, Strong naming)
- [ ] Routers: metrics (+ steps breakdown), nutrition quick-add, workouts (last-performance, active, templates, UUID upserts), running
- [ ] Strong CSV importer (NBSP/over-4 h durations, local tz, remap rules), then run the real import
- [ ] Health webhook + `health_ingest.py` (15-min buckets, merge, sleep attribution)
- [ ] Strava OAuth + sync; `scheduler.py` (Strava poll, auto-finish sweep)
- [ ] Research O2 (Health Connect forwarder)
- [ ] Tests (see SPEC §9, Phase 1)

### Phase 2: Gemini service & coach tools
- [ ] O5: verify the current Gemini model ids; configure tiers
- [ ] `ai_tools.py` (7 tools, Pydantic args, hybrid drafts), `gemini_service.py`, `routers/ai_coach.py`, `services/audio.py`

### Phase 3: Frontend & PWA
- [ ] Scaffold; Layout, RestTimer, VoiceRecorder, DraftCard
- [ ] Pages: Dashboard (steps breakdown), GymLogger (templates, auto-finish), RunningPlan, AiCoach, Settings
- [ ] PWA manifest

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
