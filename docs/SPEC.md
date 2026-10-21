# Fitness Hub — Core Specification

> Source: the original project spec (formerly the whole `CLAUDE.md`, commit `d93d650`), restructured
> on 2026-10-17 with the accepted changes from `docs/plan-review-2026-10-17.md` (decisions E0–E2,
> E4–E10). Changed or new items are tagged with their review id, e.g. **[A5]**.
> Nutrition module (Phase 5): `docs/nutrition-module-spec.md`.

## 1. Project Overview
Build a full-stack, self-hosted, mobile-first Progressive Web App (PWA) for tracking personal health metrics, gym workouts (Strong app replacement), marathon running preparation, and an integrated AI Coach powered by the Google Gemini API.
The application runs inside Docker containers and is accessed primarily via smartphone and desktop over a private network (Tailscale), **served over HTTPS via `tailscale serve`** **[A2]**.

Single user **for now**, so there are no `user_id` columns. This may become multi-user later (F4). To keep that change cheap, keep data access in per-domain service functions. When it happens, use the `Tailscale-User-Login` header that `tailscale serve` injects as the identity source.

Devices (F2): **iPhone 16 Pro** is the main phone and runs the PWA. **Galaxy Watch 6 Classic** is paired with an Android phone running Samsung Health. Runs are recorded to **Strava**. Steps come from both the watch (Samsung Health) and the iPhone (Apple Health). See §6.5.

---

## 2. Tech Stack & Strict Rules

### Backend
- **Language:** Python 3.12+
- **Framework:** FastAPI + Uvicorn
- **ORM & Validation:** SQLModel (SQLAlchemy 2.0 + Pydantic v2)
- **Database:** PostgreSQL 16 via psycopg 3 (`psycopg[binary]`). SQLAlchemy URL scheme `postgresql+psycopg://`; `config.py` normalizes a plain `postgresql://` URL **[A13]**.
- **Migrations:** Alembic **[A4]**. Never rely on `create_all` for schema changes. The first migration enables the `pg_trgm` and `unaccent` extensions (fuzzy, diacritics-insensitive matching of exercises and foods).
- **AI SDK:** `google-genai` (CRITICAL: use ONLY the new official `google-genai` package with `from google import genai`. DO NOT use the deprecated `google-generativeai` package!)
- **Data Processing:** Python built-in `csv` module (Strong CSV imports)
- **Multipart/Audio handling:** `python-multipart`; `ffmpeg` in the image for audio transcoding fallback **[A8]**
- **HTTP client:** `httpx` (Strava; later USDA/OFF)
- **Background jobs:** two small asyncio loops started in the FastAPI lifespan (`services/scheduler.py`) run Strava polling and the workout auto-finish sweep **[E9][E10]**. This replaced APScheduler during Phase 1, because two jobs need no extra dependency. Run a **single Uvicorn worker** so jobs never run twice. `SCHEDULER_ENABLED=false` turns them off (tests do this).
- **KalorickéTabulky import (Phase 5):** `kaloricketabulky-sdk` (PyPI, MIT, async, read-only), pinned to an exact version
- **Quality:** `pytest` + `httpx` (FastAPI TestClient), recorded fixtures for external APIs (Gemini, later USDA/OFF), `ruff` **[A13]**

### Frontend
- **Framework:** React 18+ with Vite and TypeScript
- **Styling:** Tailwind CSS + `lucide-react` icons
- **State & Data Fetching:** `@tanstack/react-query` (TanStack Query v5) with optimistic updates, `localStorage` persistence for active workouts, and a **persisted mutation queue** (`@tanstack/react-query-persist-client`, paused mutations resume when back online) **[A5]**
- **Charts:** `recharts`
- **Routing:** `react-router-dom`
- **PWA Support:** `vite-plugin-pwa` (configured for standalone mobile screen display)
- **Quality:** `tsc --noEmit`, ESLint **[A13]**

### Infrastructure
- **Containerization:** Docker & `docker-compose.yml`
- **Services:**
  1. `db`: `postgres:16-alpine` with persistent volume
  2. `app`: Multi-stage Docker build (Stage 1 builds React static files via Node, Stage 2 runs Python FastAPI serving `/api/*` and mounting the built React SPA at `/`). Runs `alembic upgrade head` on start. ffmpeg is a minimal static build (audio decode → FLAC only) from a pinned, signature-checked source tarball.
  3. `backup`: daily `pg_dump` into `BACKUP_DIR` (default `./data/backups`) with rotation: 7 daily / 4 weekly / 6 monthly **[A11]**. Restore steps: `docs/operations.md`.
- **Ports:** inside the container the app listens on 8000. On the host it is published **on localhost only**, at `APP_PORT` (default **8010**; host port 8000 is already taken on the server). Postgres is only published in dev (`127.0.0.1:5432`).
- **Dev loop:** `docker-compose.dev.yml` override **[A12]**, run through the `./dev` wrapper. It is a **separate compose project** (`fitness-hub-dev`) with its own database, so prod keeps running while you develop **[E14]**:
  - backend: `uvicorn --reload` with a bind mount on `127.0.0.1:${DEV_APP_PORT:-8020}`, running as the host uid so files it creates stay yours; the scheduler is off;
  - frontend (added in Phase 3): Vite dev server in a `node:22` container on `127.0.0.1:5173`, with `/api` proxied to the dev backend;
  - `scripts/seed-dev-db.sh` copies the newest prod backup into the dev database and drops the Strava tokens.

  No local Node or Python is needed.
- **HTTPS:** `tailscale serve --bg 8010` (the `APP_PORT`) → `https://<host>.<tailnet>.ts.net` serves prod; `tailscale serve --bg --https=8443 5173` serves the dev Vite server on `:8443` **[E13]**. Microphone (`getUserMedia`), camera (barcode scanning, Phase 5) and service workers (PWA install) only work in a secure context **[A2]**. Because the app is bound to localhost, plain HTTP is never reachable from the LAN.
- **No CORS:** in prod the SPA and `/api` share one origin, and in dev Vite proxies `/api`.

---

## 3. Cross-Cutting Conventions (new)
- **Time [A3]:** store all timestamps as `timestamptz` (UTC). `APP_TZ=Europe/Prague`; every "today" / day bucket is computed in that zone through one helper (`app/timeutils.py`), never with `date.today()` or naive datetimes.
- **IDs & idempotency [A5]:** entities the client creates (workouts, workout sets, meal logs, meal log items, chat conversations) have **client-generated UUID** primary keys. Create/update endpoints are idempotent upserts (`PUT .../{id}`), so retries after a dropped connection never duplicate data. Reference/server-side data (exercises, activities, plan items) keeps integer PKs.
- **Unknown ≠ 0:** values that can be missing are nullable; aggregations skip nulls and report coverage instead of treating missing as zero.
- **Language:** UI copy and AI replies in Czech; code, identifiers, comments and docs in English.
- **AI writes — hybrid save flow [E4]:** when an assistant parses dictated data, it saves directly only if everything resolves with high confidence (e.g. an exact/known exercise match and plausible numbers vs. last performance). Otherwise it returns a **draft** that the UI shows as a confirmation card; the user fixes/confirms with one tap and the client saves it through the normal CRUD endpoints. Learned mappings (aliases) are stored only on confirmation.
- **Gemini models [A7]:** never hardcode model ids. Tiers `fast` / `smart` map to `GEMINI_MODEL_FAST` / `GEMINI_MODEL_SMART` env vars; verify the live model list when implementing.
- **Webhook auth [A13]:** ingestion endpoints require an `X-Webhook-Token` header matching `WEBHOOK_TOKEN`.

---

## 4. Directory Structure

```text
fitness-hub/
├── CLAUDE.md                 # Agent guide: rules, commands, where things are
├── docker-compose.yml        # db + app + backup
├── docker-compose.dev.yml    # dev stack (project fitness-hub-dev): reload backend + Vite; run via ./dev
├── Dockerfile
├── .env.example
├── docs/
│   ├── SPEC.md               # This file
│   ├── PROGRESS.md           # Phase checklist, decisions, open questions, session log
│   ├── nutrition-module-spec.md
│   ├── plan-review-2026-10-17.md
│   └── integrations/         # Setup guides: iOS Shortcut, Health Connect forwarder, Strava app
├── backend/
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/           # Alembic env + versions
│   ├── tests/
│   └── app/
│       ├── __init__.py
│       ├── main.py           # FastAPI app init, /api/health, SPA static mount (Phase 4)
│       ├── config.py         # Settings (DATABASE_URL, GEMINI_API_KEY, model tiers, APP_TZ, WEBHOOK_TOKEN, STRAVA_CLIENT_ID/SECRET)
│       ├── database.py       # SQLModel engine, session dependency
│       ├── timeutils.py      # today()/day bounds in APP_TZ
│       ├── seed.py           # Default gym exercises seeder (idempotent)
│       ├── schemas/          # API request/response models (pydantic), one module per domain
│       ├── models/           # One module per domain [A13] (+ common.py, integrations.py)
│       │   ├── __init__.py
│       │   ├── body.py       # DailyMetric
│       │   ├── gym.py        # Exercise, Workout, WorkoutSet
│       │   ├── running.py    # Activity, TrainingPlanItem
│       │   ├── nutrition.py  # MealLog, MealLogItem (minimal in Phase 1, extended in Phase 5)
│       │   └── chat.py       # ChatConversation, ChatMessage
│       ├── routers/
│       │   ├── metrics.py    # Daily weight, steps, sleep
│       │   ├── workouts.py   # Gym workouts, sets, ghost values, Strong CSV import
│       │   ├── running.py    # Cardio activities & marathon training plan
│       │   ├── nutrition.py  # Quick-add intake (Phase 1); full module in Phase 5
│       │   ├── webhooks.py   # Health data ingestion (iOS Shortcut, Health Connect forwarder)
│       │   ├── integrations.py # Strava OAuth connect/callback/sync, integration status
│       │   └── ai_coach.py   # Coach chat, voice workout logging
│       └── services/
│           ├── gemini_service.py  # Shared google-genai runner (system prompt + toolset + history)
│           ├── ai_tools.py        # Coach tools exposed to Gemini
│           ├── workouts.py        # Workout read helpers, templates, auto-finish
│           ├── metrics.py         # Daily series with 7-day rolling averages
│           ├── strong_import.py   # Strong CSV parser/importer (+ exercise remap rules)
│           ├── strava_client.py   # Strava OAuth token refresh + activity sync
│           ├── health_ingest.py   # Step bucketing + multi-source merge, sleep attribution
│           ├── scheduler.py       # APScheduler jobs (Strava poll, workout auto-finish)
│           └── audio.py           # MIME detection + ffmpeg transcode fallback
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   └── client.ts        # Fetch wrapper & TanStack Query keys
        ├── components/
        │   ├── Layout.tsx       # Mobile bottom nav + desktop sidebar
        │   ├── RestTimer.tsx    # Floating countdown timer for gym sets
        │   ├── VoiceRecorder.tsx # MediaRecorder button sending audio to the backend
        │   └── DraftCard.tsx    # Confirmation card for AI drafts [E4]
        └── pages/
            ├── Dashboard.tsx    # Weight 7d avg chart, intake, weekly summary
            ├── GymLogger.tsx    # Active workout UI, ghost values, +/- steppers
            ├── RunningPlan.tsx  # Marathon schedule vs completed runs
            ├── AiCoach.tsx      # Chat UI + Voice workout dictation
            └── Settings.tsx     # Integrations: Strava connect/sync, last data received per source
```

---

## 5. Database Schema (`backend/app/models/`)

### 5.1 DailyMetric (table `daily_metrics`)
Intake (calories/macros) is **not** stored here — the single source of truth is `meal_logs` **[E1]**.
- `date`: `datetime.date` (Primary Key)
- `weight_kg`: `Optional[float]`
- `calories_out`: `Optional[int]`
- `steps`: `Optional[int]`: the **merged** day value. `services/health_ingest.py` keeps it up to date from §5.9/§5.10 **[E7]**. A manual entry via `POST /api/metrics` is recorded as source `manual`.
- `sleep_hours`: `Optional[float]`: the merged value, from Samsung Health sleep sessions when they exist **[E8]**
- `notes`: `Optional[str]`

### 5.2 Exercise (table `exercises`)
- `id`: `Optional[int]` (Primary Key)
- `name`: `str` (Unique, Indexed, e.g. "Bench Press (Barbell)" — same naming convention as Strong so imports match)
- `muscle_group`: `str` (chest, back, legs, shoulders, biceps, triceps, core, full_body, cardio; `arms` was split by migration 0018 [E32])
- `equipment`: `Optional[str]` (barbell, dumbbell, machine, bodyweight, cable, plate_loaded, band)
- `rep_min`, `rep_max`, `weight_step`: `Optional` progression settings for the targets **[E33]**; null = the default for the equipment (barbell / dumbbell / bodyweight 6–10 reps, 2.5 kg; machine / cable / plate_loaded 8–12, 5 kg; band / none 8–12, 2.5 kg)
- `sets_max`: `Optional[int]`: opt-in volume progression (a set is added before reps while below it); null = sets are never added **[E35]**
- `target_rir`: `Optional[int]` 0–3 (null = 1; 0 = to failure), guidance only **[E35]**
- `strategy`: `Optional[str]` `straight` (null = straight) or `top_backoff` **[E35]**

### 5.3 Workout (table `workouts`)
- `id`: `UUID` (Primary Key, client-generated) **[A5]**
- `name`: `str` (e.g. "Push Day", "Full Body")
- `started_at`: `timestamptz` (Indexed)
- `ended_at`: `Optional[timestamptz]` (null = active workout)
- `ended_by`: `Optional[str]`: `user`, `auto_idle` (auto-finish **[E9]**), or `import_estimate` (Strong duration was implausible **[E5]**)
- `source`: `str` (`manual`, `ai`, `strong_import`)
- `notes`: `Optional[str]`
- Strong re-imports are deduplicated on (`started_at`, `name`) **[A6]**.

### 5.4 WorkoutSet (table `workout_sets`)
- `id`: `UUID` (Primary Key, client-generated) **[A5]**
- `workout_id`: `UUID` (FK `workouts.id`, ondelete CASCADE)
- `exercise_id`: `int` (FK `exercises.id`)
- `exercise_order`: `int`, the position of the exercise within the workout (1-based). Added in Phase 1 for history display and templates.
- `set_order`: `int` (1, 2, 3…), the position within its exercise
- `set_type`: `str` (`normal`, `warmup`, `drop`, `failure`; replaces `is_warmup`) **[A6]**
- `weight_kg`: `Optional[float]` (0 for bodyweight; null for pure time/distance sets)
- `reps`: `Optional[int]`
- `duration_s`: `Optional[int]` (planks, timed holds, rower) **[A6]**
- `distance_m`: `Optional[float]` (rower, sled, carries) **[A6]**
- `rpe`: `Optional[float]` (1.0–10.0). The gym logger stores a confirmed RIR here (RIR-based RPE: 0 → 10, 1 → 9, 2 → 8, 3+ → 7); null = not confirmed **[E35]**
- `planned_weight_kg`, `planned_reps`: `Optional`: the target the set was planned with **[E35]**; null = no plan (imports, AI dictation, ad-hoc sets)
- `role`: `Optional[str]` `straight` / `top` / `backoff` as planned; null = no plan or outside the progression (warm-up, drop) **[E35]**
- `unusual`: `bool` (default false): the user marked this exercise's session as unusual (pain, interruption, fatigue); it is kept out of the progression **[E35]**
- `completed`: `bool` (default True)
- `completed_at`: `Optional[timestamptz]`: when the set was ticked off. This drives auto-finish **[E9]**. Null for imported sets.
- `notes`: `Optional[str]` (e.g. Strong set/exercise notes)
- `updated_at`: `timestamptz` (last-write-wins for upserts)

### 5.5 Activity (table `activities` — Running & Cardio)
- `id`: `Optional[int]` (Primary Key)
- `external_id`: `Optional[str]` (Unique, Indexed — deduplication from Strava/watches)
- `source`: `str` (default `manual`, e.g. `strava`, `samsung_health`)
- `start_time`: `timestamptz` (Indexed)
- `activity_type`: `str` (e.g. Run, Walk, Ride)
- `distance_meters`: `float`
- `duration_seconds`: `int`
- `avg_hr`: `Optional[int]`
- `max_hr`: `Optional[int]`
- `calories`: `Optional[int]`
- `notes`: `Optional[str]`

### 5.6 TrainingPlanItem (table `training_plan_items` — Marathon Prep)
- `id`: `Optional[int]` (Primary Key)
- `planned_date`: `datetime.date` (Indexed)
- `title`: `str` (e.g. "Long Run Z2", "Tempo Intervals 4x2km")
- `target_distance_meters`: `Optional[float]`
- `target_pace_sec_per_km`: `Optional[int]`
- `description`: `Optional[str]`
- `completed_activity_id`: `Optional[int]` (FK `activities.id`, nullable)

### 5.7 MealLog / MealLogItem (tables `meal_logs`, `meal_log_items`) — minimal in Phase 1 [E1]
Created in Phase 1 so intake has one home from day one; Phase 5 extends them (see the nutrition spec amendments).
- **MealLog:** `id` UUID PK (client-generated), `logged_date` date (Indexed, in `APP_TZ`), `meal_type` (`breakfast`, `morning_snack`, `lunch`, `afternoon_snack`, `dinner`, `second_dinner`, `other`). `second_dinner` matches KT's "Druhá večeře" **[G2]**., `raw_user_input` Optional[text], `notes` Optional[text], `created_at` timestamptz.
- **MealLogItem:** `id` UUID PK, `meal_log_id` UUID (FK, ondelete CASCADE), `label` str (e.g. "Rychlý zápis"), `kcal` float, `protein_g` / `carbs_g` / `fat_g` Optional[float]. Phase 5 adds `food_id` (nullable FK `foods.id`) + `amount_g`; for those items nutrients are computed live from the food, and the manual fields stay for quick-add items.

### 5.8 ChatConversation / ChatMessage (tables `chat_conversations`, `chat_messages`) [A10]
- **ChatConversation:** `id` UUID PK, `assistant` (`coach`; Phase 5 adds `nutrition`) **[E2]**, `created_at`, `updated_at`.
- **ChatMessage:** `id` PK, `conversation_id` UUID (FK, ondelete CASCADE), `role` (`user`, `model`), `content` text, `tool_calls` JSONB (names + args summary), `created_at`.

### 5.9 StepBucket (table `step_buckets`) [E7]
Interval step data per source, normalized to 15-minute buckets.
- `source`: `str` (`apple_health`, `samsung_health`)
- `bucket_start`: `timestamptz`, aligned to :00/:15/:30/:45
- `steps`: `float` (samples are split proportionally; rounding happens on the day total)
- PK (`source`, `bucket_start`)

**HealthSourceStatus** (table `health_source_status`, added in Phase 1): `source` PK, `last_received_at`, `last_day`. It records when each webhook source last delivered data, for the Settings page.

### 5.10 DailySourceMetric (table `daily_source_metrics`) [E7][E8]
Per-source daily values. Used when a source sends totals instead of intervals, and for metrics that have no buckets.
- `date`: `date` (in `APP_TZ`)
- `source`: `str` (`apple_health`, `samsung_health`, `manual`)
- `metric`: `str` (`steps_total`, `sleep_minutes`, `resting_hr`, `weight_kg`)
- `value`: `float`
- `received_at`: `timestamptz`
- PK (`date`, `source`, `metric`)

### 5.11 IntegrationToken (table `integration_tokens`) [E10]
- `provider`: `str` PK (`strava`)
- `access_token`, `refresh_token`: `str`
- `expires_at`: `timestamptz`
- `athlete_id`: `Optional[str]`
- `last_synced_at`: `Optional[timestamptz]`
- `last_activity_start`: `Optional[timestamptz]`: the cursor for incremental polling (`after=`)

---

## 6. Backend API Specification

### 6.0 Health
- `GET /api/health`: returns `{"status": "ok"}` after a DB ping (used by the Docker healthcheck).

### 6.1 Metrics (`/api/metrics`)
- `GET /api/metrics?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`: daily metrics + 7-day rolling average for `weight_kg`, plus daily intake totals (`calories_in`, protein, carbs, fat) **aggregated from `meal_logs`** with their 7-day rolling average **[E1]**.
- `POST /api/metrics`: upserts a `DailyMetric` for a given date. Only non-null fields in the payload overwrite existing fields.

### 6.2 Intake quick-add (`/api/nutrition`) [E1]
- `POST /api/nutrition/quick-add`: `{id (client UUID), date?, meal_type?, kcal, protein_g?, carbs_g?, fat_g?, label?}` → creates/upserts a `MealLog` + one `MealLogItem`. Used by the Dashboard quick input.
- `GET /api/nutrition/day?date=YYYY-MM-DD`: meals + items + day totals.
- `DELETE /api/nutrition/items/{item_id}`: idempotent delete.

### 6.3 Gym & Workouts (`/api/workouts`, `/api/exercises`)
- `GET /api/exercises`: list all exercises (seed 30 common gym exercises on startup, idempotent).
- `POST /api/exercises`: create a custom exercise.
- `GET /api/exercises/{exercise_id}/last-performance`: **CRITICAL FOR GYM UI.** Returns the sets (`set_order`, `set_type`, `weight_kg`, `reps`, `duration_s`, `distance_m`, `rpe`) from the most recent completed workout containing this exercise. Used to pre-fill "ghost values". It also carries `target`: the planned sets for the next session **[E33]** (see below).
- **Progressive overload targets [E35, replaces E33's rules]:** `services/overload.py`, no AI, details and rationale in `docs/overload-spec-review-2026-10-20.md`. Blocks: straight = all working sets; top_backoff = the first working set (top) and the rest (back-off), each progressing on its own. From the last comparable session (not `unusual`, actual weights = planned), first match wins: comeback after >21 days (~10 % lighter); weight up (+ step) when the first set reaches rep_max, middle sets rep_min and the last set rep_min − 1 (reps from the user's own sets at the new weight, else Epley for the first set and the session's drop-off for the rest; `big_jump` warning below the range); drop (a set below rep_min and ≥ 2 under its target or the previous comparable session) → repeat the target (`check_drop`, a lighter suggestion), twice in a row → one step lighter (`lower`); a target missed by 1 → `hold`; otherwise `plus_rep` on the first set below rep_max, then on the first later set under its bound (middle rep_min, last rep_min − 1); `add_set` first only when `sets_max` is set. No load: +1 rep on the weakest set, no cap. A session with a manual weight change is not comparable: the next target repeats its plan unless the same change repeats. Warnings: `stall` (4 sessions at one weight without a better total), `decline` (3 falling totals, with a deload suggestion), `big_jump`, `low_confidence` (< 2 comparable sessions). `target = {strategy, sets[{set_type, weight_kg, reps, role, changed, priority}], blocks[{role, reason, weight_kg}], warnings, suggestion{kind: deload|lighter, sets} | null, fatigue_from, stalled_sessions, days_since, settings}` or null without a usable session.
- `GET /api/workouts`: recent workouts with aggregated total volume (`sum(weight_kg * reps)` over non-warmup sets) and set count.
- `GET /api/workouts/active`: the unfinished workout (if any) with its sets, for "Resume".
- `GET /api/workouts/templates`, `PUT /api/workouts/templates/{id}` (idempotent upsert, client UUID; new ones go to the end), `DELETE /api/workouts/templates/{id}`: hand-managed templates in `workout_templates` (name, position, ordered exercises each with planned sets `{set_type, weight_kg, reps}` as JSONB) **[E18, replaces the history-derived templates of E9]**. Seeded once by migration 0010 from the latest workout of every name done ≥3 times. The client creates the new workout with its own UUID and pre-adds the exercises with the template's values (blank values fall back to `/last-performance`; the "minule" ghost stays).
- `GET /api/workouts` summaries carry `prs`: per exercise where the workout beat all earlier workouts (heaviest weight, else best Epley 1RM for ≤12 reps, else most reps on a bodyweight exercise; warm-ups excluded, the first time is never a record) **[E18]**. `DELETE /api/workouts/{id}` also discards an unfinished workout.
- **Auto-finish [E9]:** an active workout with no newly completed set for **2 h** is closed by the scheduler sweep (every 10 min) and also on any read of `/api/workouts/active`. It gets `ended_at = last set's completed_at + 2 min` (or `started_at` if there are no sets) and `ended_by = auto_idle`. The UI shows "automaticky ukončeno" and lets the user adjust it.
- `PUT /api/workouts/{workout_id}`: create-or-update a workout (client UUID); may include nested sets **[A5]**.
- `PUT /api/workouts/{workout_id}/sets/{set_id}`: create-or-update a set (client UUID) **[A5]**.
- `DELETE /api/workouts/sets/{set_id}`: idempotent delete (204 even if already gone).
- `POST /api/workouts/import-strong-csv`: accepts a CSV exported from the Strong app (`Date, Workout Name, Duration, Exercise Name, Set Order, Weight, Reps, Distance, Seconds, Notes, Workout Notes, RPE`) **[A6]**. Behaviour is tuned to the user's real export (`data/imports/strong_workouts.csv`, analysed in review §G1):
  - Format: UTF-8, comma-delimited in the real export. Still sniff `,` vs `;` as a cheap safeguard. Query param `weight_unit=kg|lbs` (default `kg`; the real export is kg).
  - `Date` is **naive local time**, so localize it in `APP_TZ` before storing it as `timestamptz`.
  - `Weight 0.0` means bodyweight. On bodyweight exercises (Pull Up, Chest Dip) a weight > 0 is **added** load. `Distance`/`Seconds` of 0 and an empty `RPE` are stored as null. Numeric `Set Order` maps to `set_type=normal` (other markers map to set types if they ever appear).
  - `Duration` such as `"1h 8m"`, `"39m"`, `"1h"` or `"2 103h 34m"` (the thousands separator is a **non-breaking space**): strip spaces and NBSP before parsing. A duration **over 4 h** is treated as a workout never finished in Strong (62 % of the real export). For those, `ended_at = started_at + set_count × 3 min` (the user's empirical average) and `ended_by = import_estimate`, and the workout is listed in `warnings`.
  - **Exercise remap rules [E5]:** the user logged some movements under the closest Strong exercise and marked them with a sticky note on set 1. Each rule is `{strong_name, map_to, muscle_group, equipment?, marker_note?, all_workouts}`. It applies to every set of that exercise, in all workouts, or with `all_workouts=false` only in workouts where the marker note appears. The marker note is dropped from the imported sets. Default rules:
    - `Lat Pulldown (Machine)` → **Bent-over Pulldown** (back), all workouts (the note is on 41/41).
    - `Lat Pulldown - Underhand (Cable)` → **Kelso Shrug** (back), all workouts. This is an assumption: the note first appears on 2025-09-30, but loads continue seamlessly from the note-less workouts before it.
    - Rules can be overridden per import via an `exercise_map` JSON field.
  - Any other notes are kept in `WorkoutSet.notes`.
  - Missing exercises are auto-created. The seed already covers all 42 exercises of the real export with muscle groups, so this should only happen for future exercises. Workouts already imported are skipped (dedupe on `started_at` + `name`).
  - Returns `{workouts_created, workouts_skipped, sets_created, exercises_created, warnings[]}`.
  - Tests run against a small anonymized slice of the real export, covering an NBSP duration, an over-4 h duration, the remap rules and bodyweight sets.

### 6.4 Running & Marathon Plan (`/api/running`)
- `GET /api/running/activities`: cardio activities with calculated pace (min/km).
- `GET /api/running/activities/{id}` [E29]: run detail page — summary, chart series (≤ 400 points: distance, pace, GAP, HR, altitude, cadence, lat/lng), per-km splits on moving time, simplified route, zones. Missing or outdated streams are fetched from Strava first (best effort, 2 requests).
- `POST /api/running/activities`: log a run manually (Strava-synced runs arrive via §6.5; dedupe on `external_id`).
- **Strava is the only automatic source of activities [E10].** Samsung Health and Apple Health workouts are not ingested, so runs are never duplicated.
- `GET /api/running/plan?start_date=...&end_date=...`: planned marathon workouts alongside linked actual activities.
- `POST /api/running/plan`: create/update a planned run.

### 6.5 Health & activity data ingestion (`/api/webhooks`, `/api/integrations`)

**Sources**
| Data | Source | Path |
|---|---|---|
| Runs (+ HR, calories) | Strava | OAuth app + **polling**, no public webhook **[E10]** |
| iPhone steps | Apple Health | **iOS Shortcuts** personal automation → `POST /api/webhooks/health` **[E6]** |
| Watch steps, sleep | Samsung Health → Health Connect (on the Android phone paired with the watch) | **Life Dashboard Companion** app on that phone → `POST /api/webhooks/health-connect` **[E8, O2]** |

**Strava [E10]**
- `GET /api/integrations/strava/connect` redirects to Strava authorize (scope `activity:read_all`). `GET /api/integrations/strava/callback` exchanges the code and stores it in `integration_tokens`. The redirect runs in the browser, so the tailnet hostname works as the callback domain and nothing is exposed publicly.
- `POST /api/integrations/strava/sync`: manual sync. The scheduler also syncs every 30 min, plus once when the app is opened.
  - It is incremental via `after=last_activity_start`. The first run backfills the full history page by page.
  - It refreshes the access token when it has expired. It maps each activity to `Activity` with `external_id = "strava:<id>"`, `source = strava`, and fetches details (calories) only for new activities.
  - It stays far below Strava's rate limits.
- `GET /api/integrations/status`: Strava configured/connected + last sync, whether webhooks are enabled, and the last payload received per webhook source.
- **Not configured = refused, never silent:** without `STRAVA_CLIENT_ID`/`SECRET`, connect returns 503. Without `WEBHOOK_TOKEN`, webhooks return 503. Sync without a connection returns 409.

**`POST /api/webhooks/health`**: `X-Webhook-Token` required **[A13]**.
```json
{
  "source": "apple_health",
  "days": ["2026-10-16", "2026-10-17"],
  "steps": [{"start": "2026-10-17T08:03:00+02:00", "end": "2026-10-17T08:11:00+02:00", "count": 812}],
  "daily": [{"date": "2026-10-17", "metric": "steps_total", "value": 8123}],
  "sleep_sessions": [{"start": "2026-10-16T23:40:00+02:00", "end": "2026-10-17T06:55:00+02:00"}]
}
```
- **Replace semantics:** a push carries the **complete** data of that `source` for each listed day. The server replaces that source's buckets, daily values and sessions for those days, so repeated pushes are idempotent. Senders always include **yesterday and today**, which catches steps around midnight and late syncs.
- Every field except `source`/`days` is optional. Each sender sends what it can (intervals preferred, daily totals as fallback).

**Step merge algorithm [E7]** (`services/health_ingest.py`, re-run for each affected day after every push)
1. Interval samples are distributed into **15-min buckets** (`step_buckets`) in proportion to their time overlap. Samples **longer than 1 hour** carry no usable timing (Samsung Health writes one whole-day record to Health Connect), so they never enter the buckets: their in-day part is stored as the source's `steps_untimed` daily value and only adds to that source's daily total **[E38]**.
2. **Day total = the source with the most steps [E39]:** each source's total is its bucket sum plus its untimed steps, or its own daily total when that is higher, and the day takes the **max** over sources. There is no per-bucket merge: with untimed watch data it inflated the day. The buckets remain for the breakdown chart.
4. The result is written to `DailyMetric.steps`. `GET /api/metrics/steps-breakdown?date=` returns per-source totals, the method used (`max_daily`, `single_source` or `manual`), the merged total and the merged bucket series, so the number is explainable.

**Sleep [E8]:** sleep sessions are attributed to the **date of wake-up** (session end, in `APP_TZ`). `DailyMetric.sleep_hours` is the total of all sessions ending on that date, naps included. Samsung Health is the primary sleep source.

**Sender setup** (guides to be written in `docs/integrations/` during Phase 4, once the HTTPS URL exists):
- **iOS Shortcut [E6]:** one shortcut, triggered by several "Time of Day" personal automations set to run without asking (e.g. 12:00, 18:00 and 23:30), and also runnable by hand.
  - It uses `Find Health Samples` for Steps with Start Date today/yesterday and Source = this iPhone, so it doesn't re-send other apps' data.
  - It builds the JSON with each sample's start, end and count and runs `Get Contents of URL` (POST plus the token header).
  - Tailscale on-demand must be enabled on the iPhone.
- **Health Connect forwarder [E8, O2]:** [Life Dashboard Companion](https://github.com/owen282000/life-dashboard-companion-app). It's MIT-licensed, with a signed APK on GitHub Releases or Obtainium (F-Droid is in review). It runs on the Android phone the watch is paired with. It was chosen because:
  - it sends **per-record steps with start/end** (needed for the bucket merge) and sleep sessions;
  - it supports custom headers and an HMAC signature;
  - it keeps an offline outbox for a week;
  - it can backfill 30, 90 or 365 days, which replaces the one-off Samsung CSV import.

  Setup on the phone:
  - Enable Samsung Health → Health Connect sync. Install Tailscale.
  - In the app, enable only *Steps* and *Sleep*, and keep the steps resolution at "every record".
  - Webhook URL `https://<host>.ts.net/api/webhooks/health-connect`, with either the custom header `X-Webhook-Token: <WEBHOOK_TOKEN>` or an HMAC secret (= `HEALTH_CONNECT_SECRET`).
  - Run a 365-day backfill once.
- **`POST /api/webhooks/health-connect`** is the receiver for that app's documented payload (`docs/webhook.md` in its repo):
  - Syncs are **incremental**, so raw step and sleep records are stored by their stable `uuid` (table `health_records`), deletions in `deleted_records` are applied, and each touched day is rebuilt from all stored records into `step_buckets` and sleep minutes. That makes repeated, edited and late payloads harmless.
  - Only records written by `HEALTH_CONNECT_ORIGINS` count (default Samsung Health, `com.sec.android.app.shealth`; `*` = all), so a second app writing the same steps can't double-count.
  - `daily_totals` are stored as the source's daily total, and the highest `sequence` per date wins.
  - Complete steps buckets are stored, incomplete ones are skipped. Test pings and Screen Time payloads return 200 and are ignored.
  - Its iOS app sends the same format with `source: healthkit_ios`, which maps to `apple_health`. That is a possible later replacement for the iOS Shortcut.
  - Known limit: a backfill window's "complete" marker isn't used to infer deletions. Only explicit `deleted_records` remove data.

### 6.6 AI Coach & Voice Dictation (`/api/ai`)
The coach is one of **two separate assistants** (the nutrition assistant arrives in Phase 5) **[E2]**. Both use the shared runner in `gemini_service.py` with their own system prompt and toolset.
- `POST /api/ai/chat`:
  - Accepts `message: str`, `model: "fast" | "smart"` (default `fast`) **[A7]**, optional `conversation_id`.
  - Loads prior messages of the conversation from the DB as history, executes Gemini with function-calling tools, stores the new turn **[A10]**.
  - Returns `reply: str`, `conversation_id`, `tool_calls_made: list[str]`, `drafts: list` **[E4]**.
- `GET /api/ai/conversations/{conversation_id}`: message history (for continuing a chat on another device).
- `POST /api/ai/voice-workout`:
  - Accepts `UploadFile` (audio recorded on mobile: Android Chrome → `audio/webm;codecs=opus`, iOS Safari → `audio/mp4`; also mp3/wav/m4a/ogg) OR `text: str`, plus `workout_id: Optional[UUID]`.
  - Audio handling **[A8]**: first verify whether Gemini accepts webm/mp4 directly; if a MIME type isn't accepted, transcode with ffmpeg to FLAC 16 kHz mono (`services/audio.py`).
  - Uses Gemini multimodal input to parse spoken Czech/English workout dictation (e.g. "Bench press první série 80 kilo 10 opakování, druhá 85 kilo 8 opakování, RPE 8").
  - Applies the hybrid save flow **[E4]**: returns `saved_sets` and/or `drafts` for 1-tap confirmation.

### 6.7 Coach knowledge base: RunningCoach (`/api/coach`) [E11]
- The user's GitHub repo `COACH_KB_REPO` (PavelJanosekk/RunningCoach) **stays the source of truth**; the user keeps their Claude Code workflow there. The app keeps a read-only copy of its root `*.md` files (`coach_documents`). It syncs every 6 h and via `POST /api/coach/kb/sync`; git blob SHAs skip unchanged files. A failure is recorded and keeps the previous copy.
- Parsed into tables on each sync, forgivingly (unparsed rows become warnings, never errors):
  - the weekly plan tables of `04_timeline_plan.md` → `training_weeks` (km/LR ranges, quality, block, notes; years inferred from the "Aktualizováno" date);
  - races and goals from `00_INDEX.md` → `races` (`source = kb`, replaced on each sync; races the user removed stay hidden, matched by name + date) **[E34]**;
  - LTHR and max HR → `athlete_profile`.

  A changed LTHR triggers a local recompute of all run metrics.
- Coach context: `CLAUDE.md`, `00_INDEX.md`, `02_physiology_zones.md` and `11_errata_corrections.md` go into every system instruction; the rest is read via `read_knowledge_base`. The coach is told the KB is read-only and that its script/commit instructions don't apply to it.
- `GET /api/coach/kb` (status, docs, races, LTHR, warnings), `GET /api/coach/kb/documents/{name}`, `GET /api/running/weeks` (plan vs actual: km, runs, longest run per week).
- Races can also be managed in the app **[E34]**: `POST /api/coach/races` adds one (`source = user`, untouched by syncs), `DELETE /api/coach/races/{id}` deletes a user race or hides a KB race (`hidden`). Hidden races are left out of the Run page, the coach context and the marathon boss.

### 6.8 Run stream metrics [E12]
- Port of RunningCoach `scripts/metrics.py` (`services/run_metrics.py`): Minetti GAP, pace of the first 10 min, steady HR (after 10 min), EF (GAP m/min per beat), decoupling (GAP/HR, first vs second steady half), seconds per zone (% of LTHR as in `02`), share above easy/steady, GAP within the easy comparison band (83–87 % LTHR = 143–150).
- The Strava sync fetches detail (RPE, description, calories) and per-second streams for runs, **newest first, 10 per sync**, so the history backfills within rate limits. Activities from the last 36 h get their detail re-read, because the fueling log and pain notes are added later. Raw streams are stored (`activity_streams`) so metrics can be recomputed without API calls. Streams also include `altitude`, `cadence` and `latlng` for the run detail (E29); `activity_streams.keys` records the requested keys, and rows fetched with fewer keys are refetched within the same per-sync budget (missing streams first).

---

### 6.9 Data export into the analysis repo (`/api/export`) [E40]
- `EXPORT_REPO` (+ `EXPORT_BRANCH`, `EXPORT_DIR` = `fitness-hub`, `EXPORT_HOUR` = 4) with `GITHUB_TOKEN`; unset = disabled. The token also authenticates the KB sync (§6.7).
- `services/repo_export.py` builds deterministic files: `activities.csv` (every activity + stream metrics, paces in s/km, zones in minutes), `gym_workouts.csv`, `gym_sets.csv` (RIR = 10 − stored RPE), `nutrition_items.csv`, `nutrition_daily.csv` (with `items_missing_kcal`), `daily_metrics.csv` (merged weight/steps/sleep + lowest resting HR), `weeks.csv` (Mon–Sun, plan from `training_weeks`, averages only over days with data), `profile.md`, `README.md` (Czech column guide). Unknown values stay empty cells.
- One commit through the Git Data API (blobs → tree on the head's tree → commit → non-forced ref update). Unchanged blobs (local git blob sha) are skipped; no change = no commit. Files in the folder the export no longer writes are deleted; the rest of the repo is never touched.
- A public repo is refused (`PublicRepoError`) unless the user confirmed it: `POST /api/export/sync?confirm_public=true` stores `repo_export_state.public_ok_repo`; without it the endpoint answers 409 `{"code": "public_repo", "repo"}` and Nastavení shows a confirmation modal. `DELETE /api/export/public-consent` revokes it. `GET /api/export` = status (`public_ok`, last success/error/commit).
- Scheduler: an hourly check runs the export once per local day after `EXPORT_HOUR`; a failure is retried the next hour.

### 6.10 Daily kcal target from running (`/api/nutrition/targets`) [E41]
- `services/nutrition/targets.py`: `day_target(day)` = base + Σ k·weight·km (the day's runs except LR) + ½·weight·km of today's LR + ½ of tomorrow's **planned** LR, rounded to 50 kcal half up; k = 0.75 easy/strides/hills, 1.0 threshold/LR. Weight = mean of the weigh-ins of the 7 days up to the day, else the last known one; no weight = no run kcal. Protein and fat from the profile, carbs = (kcal − 4·P − 9·F)/4 half up. Gym adds nothing.
- Runs: the day's `training_days` line (midpoint of a km range) typed by keywords (long run/LR, threshold/tempo/T, kopce, strides, else easy). Strava runs of the local day replace planned ones in order and keep the planned type; extra runs are easy. Nothing is frozen: every day is computed on demand.
- Modes (code constants): 2026-10-21 cut, 2026-12-21 maintenance, 2027-01-04 cut, 2027-01-28 off, 2027-02-15 maintenance. Maintenance base = base + `maintenance_offset_kcal` (null = 500); off = no kcal/macro targets.
- Profile (`/api/nutrition/profile`): `kcal_target` = base, `protein_target_g`, `fat_target_g`, `maintenance_offset_kcal`, `fiber_target_g` (migration 0026 drops `kcal_target_training_day` and `carbs_target_g`).
- Base proposal (cut, Mondays from 2026-11-09, anchored on the week's Monday): resting HR 7-day mean ≥ median of the previous 28 days + 5 → +200 (≥3 readings each); else weight trend (7-day mean now vs 14 days earlier)/2: < −0.6 kg/week → +150, > −0.2 → −100 (not below 1900). `GET /api/nutrition/targets?date=` returns today, tomorrow and the proposal; `POST /api/nutrition/targets/proposal {accept}` accepts or dismisses it for the week (`base_proposal_handled_on`).
- Meal type `fueling` ("Během běhu"): in the totals, excluded from % of target; `DaySummary.fueling_kcal`, `target` (breakdown). Resting HR: `POST /api/metrics {resting_hr}` stores a manual `daily_source_metrics` row; Přehled has the field next to weight (the quick kcal entry is gone).
- Export: `targets_daily.csv` (2026-10-21 → tomorrow), `fueling_kcal` in `nutrition_daily.csv`, formula and modes in `profile.md`.

### 6.11 Quick actions on Jídlo (`/api/nutrition/quick-actions`) [E42]
- `quick_actions`: client UUID, `name`, `emoji`, `color` (accent palette name: emerald / amber / red / sky / violet, themed per theme), `meal_type` (fixed), `start_minute` < `end_minute` (minutes of the local day, 0–1440), `position`. `quick_action_items`: ordered `food_id` (FK, RESTRICT: a food used in an action can't be deleted) + `amount_g`.
- `GET` lists actions by position with each item's food name, kcal and protein and the action's totals. `PUT /{id}` upserts the action and replaces its items (1–15, unknown food = 422). `DELETE /{id}`. `POST /{id}/log {date, item_ids}` logs every item into the day's meal of the action's type through the normal item upsert; the client ids (one per item) make a retry harmless, and the undo deletes those items.
- Jídlo: the actions whose window contains the current local time are big tinted cards (emoji, name, items, kcal / protein, +). A tap logs into the open day and shows a toast with Zpět. **Vše** lists all actions by relevance (in the window first, then by the circular distance to the window), each with add and edit, plus *Nová rychlá akce*. The editor: name, emoji, color, meal (changing it re-fills an untouched window), from–to, foods with grams (local food search), live totals, delete. Page order on Jídlo: summary, quick actions, Jídla, assistant, vitamins. **Done for the day:** logged items carry `meal_log_items.quick_action_id` (migration 0028, FK SET NULL, old items unmarked), and an action whose items are in the open day is hidden from the cards after its check + fold animation; *Vše* marks it *Zapsáno* (adding again stays possible). Zpět or deleting the items brings it back. When every in-window action is done the strip says *Na teď máš zapsáno* + the next one. The assistant card has no suggested prompts (user).
- Migration 0027 seeds *Vločky s proteinem* (50 g `ovesné vločky` + 30 g Just whey, breakfast 5:00–11:00, amber) and *Tvaroh s proteinem* (250 g `Tvaroh polotučný 3,8% Pilos` + 30 g Just whey, afternoon snack 14:00–18:00, sky) when those foods exist.

## 7. Gemini Coach Implementation (`backend/app/services/`)

**IMPORTANT FOR AGENT:** the code is the reference. Read it rather than re-deriving it from an old sample.
- **`gemini_service.py`:** the shared runner for both assistants. It uses `client.chats.create(model, config, history)` + `send_message(parts)` with automatic function calling, which is the SDK's recommended path. In chat mode the SDK records every function-call round in the **chat history**, so `tool_calls_made` is read from `chat.get_history()` after the prior turns, **not** from `response.automatic_function_calling_history` (always empty in chat mode). Tier → model + thinking level from env **[A7]**. Errors: missing config → 503, Gemini 429 → 429, other API errors → 502.
- **`coach.py`:** one coach turn. Loads the last 30 messages of the conversation as text history, builds the system instruction, runs the runner, stores both messages (with the tool calls) **[A10]**. System instruction = Czech coach role and rules + today with weekday and Mon–Sun week + exact exercise catalog (so dictated names map to exact matches) + the **knowledge-base core** (§6.7) **[E11]**.
- **`ai_tools.py`:** coach tools as closures over a `ToolContext` (session, now, drafts, saved sets). Structured arguments are Pydantic models (`SetInput`). Typed `list[BaseModel]` arguments were verified live **[A9]**.

### Coach tools
| Tool | Purpose |
|---|---|
| `get_calendar(start_date?, days)` | Dates with Czech weekday and Mon–Sun week. The KB errata forbid computing weekdays "from your head". |
| `get_body_metrics_summary(days)` | Weight + 7-day average, intake from meal logs **[E1]**, steps, sleep, averages |
| `get_muscle_group_volume(days)` | Working sets and tonnage per muscle group, plus untrained groups |
| `get_exercise_progression(name, weeks)` | Top set and e1RM per session (pg_trgm/unaccent name match) |
| `get_running_and_marathon_context(days)` | Runs with stream metrics, RPE, description and heat flag; weekly km; HR zones from LTHR; races with days to go; plan weeks; leg workouts |
| `get_efficiency_trend(weeks)` | GAP in the easy HR band and EF per month and per run, at equal HR and grade; heat runs and quality sessions excluded **[E12]** |
| `read_knowledge_base(document)` | Full text of a KB document ("04", "07_nutrition.md", …) |
| `log_workout_sets_from_ai(exercise_name, sets, workout_id?)` | Hybrid flow **[E4]**: exact name and plausible numbers are saved; fuzzy/unknown names or weights outside 0.5–1.3× the last session become drafts |
| `log_daily_metric_from_ai(weight, steps, sleep)` | Manual values, which win over devices |
| `log_quick_intake_from_ai(kcal, macros)` | Quick-add meal item **[E1]** |

## 8. Frontend Requirements (Mobile-First PWA)
Clean, dark-mode default UI (Tailwind slate-900 / zinc-900 background) optimized for one-handed operation in the gym. Requires the HTTPS origin from `tailscale serve` for microphone and PWA install **[A2]**.

**Themes [E19]:** three switchable looks in Nastavení → Vzhled, stored per device: *Minimalistický* (the default dark zinc/emerald UI), *Moderní* (dark glass over an aurora, violet accent, rounded type) and *Zen* (light washi paper, sumi ink, matcha accent, serif headings). Themes remap the palette names the pages use (`src/index.css`); charts take a validated color set per theme.

**Bottom Navigation Bar:** Dashboard (Home / Trends), Gym (Active Workout & History), Run (Activities & Marathon Plan), AI Coach (Chat & Voice Dictation). Phase 5 adds a 5th tab "Jídlo".

**Gym Logger Page (`GymLogger.tsx`) — key UX features:**
- **Start Workout / Resume Active Workout:** active workout state mirrored in `localStorage`; workouts and sets get client UUIDs and every change goes through the persisted mutation queue, so a dropped signal in a basement gym loses nothing and retries never duplicate **[A5]**.
- **Templates [E18, was "Start from last …" E9]:** the start screen lists the saved templates ("Chest tri", "Back biceps", …). Tapping one opens its detail (exercises with planned kg × reps) with **Začít trénink** (creates the workout with everything pre-filled), **Upravit** (editor: name, exercise order/add/remove, sets with kg × reps) and **Smazat** **[E31]**; "+ Nová šablona" creates one. In the active workout every exercise has a trash button (asks first when it has checked sets). "Empty workout" remains available.
- **Discard [E18]:** an unfinished workout can be discarded from the resume card and from the active screen; it deletes the workout and its sets on the server (queued like other gym writes) and on the phone.
- **History [E18]:** paged list (8 per page) with PR badges ("Bench Press PR"); a row opens a read-only view laid out like the active workout, with PR details and a delete button.
- **Auto-finish [E9]:** a forgotten workout closes itself after 2 h with no sets (see §6.3). The history marks it as "automaticky ukončeno" with an editable end time.
- **Ghost Values:** when an exercise is added, fetch `/api/exercises/{id}/last-performance` and show the previous session's weight & reps in the "Minule" column (tap = copy).
- **Targets [E33, E35]:** the sets are pre-filled with the target and its plan is kept with each set (template values only fill exercises without history; the template's working-set count wins). A line under the exercise name shows the target and the reason of each block (*+1 opakování*, *Zvýšení váhy*, *Back-off progres*, *Návrat na vyšší váhu*, *Udržet cíl*, *Prověřit propad*, *Snížit váhu*, *Po pauze*, *Málo dat*); the priority set is marked. Tapping it explains the rules, offers suggestions for today only (*Použít dnes*), the *Neobvyklý průběh* toggle and the exercise's progression settings (also in Cviky). Under a ticked set: the target when the actual differs, and a 0 / 1 / 2 / 3+ RIR picker (never required; nothing selected = not confirmed). Changing a weight offers to copy it to the following unticked sets of the same block (*Vrátit* undoes it, *I příště* makes it the plan).
- **Quick Stepper Controls:** −2.5 / +2.5 buttons for weight and −1 / +1 for reps next to the inputs, so the keyboard is rarely needed. Set type toggle (W / D / F) **[A6]**.
- **1-Tap Complete & Rest Timer:** the checkmark marks the set completed, sends an optimistic mutation, and starts the floating `RestTimer` (60 / 90 / 120 / 180 s with a progress bar).
- **Voice Dictation Shortcut:** floating microphone button (`VoiceRecorder.tsx`) inside the active workout; drafts appear as `DraftCard`s **[E4]**.

**Dashboard Page (`Dashboard.tsx`):**
- Quick input card at the top: "Dnešní váha (kg)" (→ `POST /api/metrics`) & "Rychlý zápis kcal" (→ `POST /api/nutrition/quick-add` **[E1]**) with instant save.
- Chart 1 (Recharts `ComposedChart`): daily weight (dots) with a smooth 7-day rolling average line + daily caloric intake bars.
- Chart 2: weekly gym volume by muscle group & weekly running mileage (km).
- Steps & sleep tile: the merged daily steps. Tapping it shows the per-source breakdown (iPhone vs. watch, merge method) from `/api/metrics/steps-breakdown` **[E7]**.

**Settings Page (`Settings.tsx`)** (gear icon on the Dashboard, plus an item in the desktop sidebar; not a bottom tab):
- Strava: connect button, connection state, last sync, "Synchronizovat teď" **[E10]**.
- Webhook sources: last payload received per source (`apple_health`, `samsung_health`), so a broken Shortcut or forwarder is noticed.
- Strong CSV import (file picker + result summary with warnings).

**AI Coach Page (`AiCoach.tsx`):**
- Model tier toggle at top: Rychlý (zápis & dotazy) vs. Hloubkový (analýza) → `fast` / `smart` **[A7]**.
- Quick prompt chips:
  - "Analyzuj moji stagnaci a objem partií za poslední měsíc"
  - "Zhodnoť můj běžecký plán na tento týden vůči únavě z fitka"
- Text input + hold/tap-to-record audio button using `navigator.mediaDevices.getUserMedia` and `MediaRecorder` (pick a supported MIME via `MediaRecorder.isTypeSupported`).
- Conversation persisted server-side; drafts rendered as `DraftCard`s **[A10][E4]**.

---

## 9. Implementation Phases
Execute in order, verifying each before moving on. Track status in `docs/PROGRESS.md`.

**Phase 0 — Scaffolding & dev loop (new)**
- Backend skeleton (`config.py`, `database.py`, `timeutils.py`, `main.py` with `/api/health`), `requirements.txt`.
- Alembic setup + initial migration enabling `pg_trgm` and `unaccent` (+ `f_unaccent()` immutable wrapper for indexes).
- `Dockerfile` (`dev` and minimal `prod` stages), `docker-compose.yml` (db + app), `docker-compose.dev.yml` (backend reload); `.env.example`; pytest (dedicated `<db>_test` database, rolled-back transaction per test) + ruff (incl. `DTZ` naive-datetime rules); full dependency freeze in `backend/constraints.txt`.

**Phase 1 — Backend core & database**
- All models from §5 (incl. minimal meal tables, chat tables, step buckets, daily source metrics, integration tokens) + migrations. The idempotent exercise seed covers all 42 exercises of the real Strong export with muscle groups, plus common extras.
- Routers: `metrics.py` (+ steps breakdown), `nutrition.py` (quick-add), `workouts.py` (`/last-performance`, `/active`, `/templates`, UUID upserts, Strong importer with remap rules), `running.py`, `webhooks.py` (health ingestion + merge), `integrations.py` (Strava OAuth + sync).
- `scheduler.py`: Strava poll every 30 min, auto-finish sweep every 10 min.
- Research: choose the Health Connect forwarder app for the Android phone **[E8]**.
- Tests:
  - upsert idempotency, last-performance, templates, auto-finish;
  - Strong import (anonymized slice of the real export);
  - step merge (overlapping buckets, single source, daily-total fallback);
  - sleep attribution;
  - Strava mapping (recorded fixtures);
  - timezone day bucketing.
- Run the real Strong import against the dev DB and check the summary.

**Phase 2 — Gemini AI service & coach tools**
- Verify the current Gemini model ids; configure tiers.
- `ai_tools.py` (10 coach tools, Pydantic args, hybrid drafts), `gemini_service.py` (shared runner), `coach.py`, `routers/ai_coach.py` (text + audio, conversation persistence), `services/audio.py`.
- RunningCoach knowledge-base sync + parsing (§6.7) and run stream metrics (§6.8), added in Phase 2 by decisions E11/E12.

**Phase 3 — React frontend & PWA**
- Scaffold with Vite, React, TypeScript, Tailwind, lucide-react, TanStack Query (+ persist client), recharts. Add the Vite dev service (`node:22`, `/api` proxy) to `docker-compose.dev.yml`.
- `Layout.tsx`, `RestTimer.tsx`, `VoiceRecorder.tsx`, `DraftCard.tsx` and the 4 pages; `vite-plugin-pwa` manifest.

**Phase 4 — Dockerization & deploy**
- Multi-stage `Dockerfile` (frontend build stage, ffmpeg), `docker-compose.yml` (db + app on `127.0.0.1:${APP_PORT}` + backup), healthcheck on `/api/health`.
- Refresh `backend/constraints.txt` if dependencies changed (it has been frozen since Phase 0; see CLAUDE.md "Dependencies").
- FastAPI serves the built React `dist/` as an SPA fallback so refreshing any route works.
- `tailscale serve --bg 8010`; verify mic + PWA install on the iPhone over HTTPS.
- Integration setup with guides in `docs/integrations/`:
  - register the Strava API app and connect it;
  - build the iOS Shortcut and its automations;
  - install and configure the Health Connect forwarder plus Tailscale on the Android phone.

  Verify that data arrives from every source (Settings page).

**Phase 5 — Nutrition module**
- Per `docs/nutrition-module-spec.md`, including its "Amendments" section.

---

## 10. Commands & Verification
- Dev stack (project `fitness-hub-dev`): `./dev up -d --build`; seed its DB from prod with `scripts/seed-dev-db.sh`
- Migrations: `./dev exec app alembic revision --autogenerate --rev-id 000N -m "<msg>"` (sequential ids), `./dev exec app alembic upgrade head` (also runs on every app start, in prod too)
- Tests / lint: `./dev exec app pytest`, `./dev exec app ruff check .`, frontend `npm run typecheck`
- Production (project `fitness-hub`): `docker compose up -d --build`; logs `docker compose logs -f app`; backups and restore in `docs/operations.md`
- Health: `curl -f http://127.0.0.1:8010/api/health && curl -f http://127.0.0.1:8010/api/exercises` (dev: port 8020)
- HTTPS over the tailnet: `tailscale serve --bg 8010` (prod), `tailscale serve --bg --https=8443 5173` (dev)
- Always verify container health and fix any startup tracebacks before finishing a phase.
