# Progress

**Current phase:** Phase 0 — not started (specs finalized, no code yet).
**Next step:** Phase 0 scaffolding (`docs/SPEC.md` §9). Ask the open questions below that block upcoming work.

## Decisions
| Id | Date | Decision |
|---|---|---|
| E0 | 2026-10-17 | Apply all core fixes A1–A13 from the review; docs split into CLAUDE.md / docs/SPEC.md / docs/PROGRESS.md. |
| E1 | 2026-10-17 | Intake lives only in `meal_logs`/`meal_log_items`. `DailyMetric` has no calories_in/macros; the dashboard "kcal" input is a quick-add meal item. Minimal meal tables ship in Phase 1. |
| E2 | 2026-10-17 | **Two separate assistants** (coach, nutrition), shared Gemini runner, separate prompts/toolsets/conversations. Coach only reads intake totals. |
| E3 | — | *Pending (decide before Phase 5):* USDA bulk-seed locally (recommended) vs. lazy API lookup. |
| E4 | 2026-10-17 | Hybrid save flow for AI-parsed data: auto-save only on high-confidence/confirmed matches, otherwise a draft card for 1-tap confirmation; aliases learned only on confirmation. |

## Open questions
| Id | Question | Blocks |
|---|---|---|
| F1 | Real Strong CSV export → `data/` | Strong importer (Phase 1) |
| F2 | Phone (Android/iPhone) + watch/platform (Garmin, Samsung, Strava, Apple Health…) | Webhook payloads (Phase 1) |
| F3 | KalorickéTabulky: Premium? Any export (format) or GDPR data request? | KT importer (Phase 5) |
| F4 | Single user only? (assumed yes — no `user_id`) | Schema (Phase 1) |
| F5 | Commit progress to git as we go? | — |

## Phase checklist

### Phase 0 — Scaffolding & dev loop
- [ ] Backend skeleton: `config.py`, `database.py`, `timeutils.py`, `main.py` + `/api/health`, `requirements.txt`
- [ ] Alembic + initial migration (`pg_trgm`, `unaccent`)
- [ ] `docker-compose.yml` (db) + `docker-compose.dev.yml` (reload backend, Vite in `node:22`)
- [ ] `.env.example`; pytest + ruff wired up

### Phase 1 — Backend core & database
- [ ] Models (§5): DailyMetric, Exercise, Workout, WorkoutSet, Activity, TrainingPlanItem, MealLog/MealLogItem (minimal), ChatConversation/ChatMessage + migration
- [ ] Idempotent exercise seed (30, Strong naming)
- [ ] Routers: metrics, nutrition quick-add, workouts (last-performance, active, UUID upserts), running, webhooks
- [ ] Strong CSV importer (needs F1)
- [ ] Tests: upsert idempotency, last-performance, Strong import, timezone bucketing

### Phase 2 — Gemini service & coach tools
- [ ] Verify current Gemini model ids; configure tiers
- [ ] `ai_tools.py` (7 tools, Pydantic args, hybrid drafts), `gemini_service.py`, `routers/ai_coach.py`, `services/audio.py`

### Phase 3 — Frontend & PWA
- [ ] Scaffold; Layout, RestTimer, VoiceRecorder, DraftCard; Dashboard, GymLogger, RunningPlan, AiCoach; PWA manifest

### Phase 4 — Docker & deploy
- [ ] Multi-stage Dockerfile (ffmpeg), compose (db, app, backup), healthcheck, SPA fallback
- [ ] `tailscale serve`; verify mic + PWA install on the phone

### Phase 5 — Nutrition module
- [ ] Decide E3; then steps 1–6 of `docs/nutrition-module-spec.md` with its Amendments

## Backlog (ideas, not accepted)
- D1 `Exercise.secondary_muscles` for better volume analysis
- D2 Race goal + AI-generated marathon plan; auto-link activities to plan items
- D3 Progressive-overload suggestion alongside ghost values
- Adaptive TDEE from weight trend + intake (AI coach tool)
- NutriDatabáze.cz as a Czech food source (licensing unverified)

## Session log
- **2026-10-17** — Reviewed the original spec and the user's nutrition module spec; live-checked USDA FDC and Open Food Facts APIs. Saved the nutrition spec (`docs/nutrition-module-spec.md`), wrote the review (`docs/plan-review-2026-10-17.md`), got decisions E0/E1/E2/E4, restructured docs (CLAUDE.md → short guide; `docs/SPEC.md` = fixed + amended core spec; nutrition amendments added). Nothing committed yet.
