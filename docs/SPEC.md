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
- **Background jobs:** APScheduler `AsyncIOScheduler`, started in the FastAPI lifespan, runs Strava polling and the workout auto-finish sweep **[E9][E10]**. Run a **single Uvicorn worker** so jobs never run twice.
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
  2. `app`: Multi-stage Docker build (Stage 1 builds React static files via Node, Stage 2 runs Python FastAPI serving `/api/*` and mounting the built React SPA at `/`). Runs `alembic upgrade head` on start.
  3. `backup`: daily `pg_dump` into `./data/backups` with rotation (e.g. 7 daily / 4 weekly / 6 monthly) **[A11]**
- **Dev loop:** `docker-compose.dev.yml` override — backend with `uvicorn --reload` and a bind mount, frontend with the Vite dev server (`node:22` image, `/api` proxied to the backend). No local Node/Python needed **[A12]**.
- **HTTPS:** `tailscale serve --bg 8000` → `https://<host>.<tailnet>.ts.net`. Required: microphone (`getUserMedia`), camera (barcode scanning, Phase 5) and service workers (PWA install) only work in a secure context **[A2]**.

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
├── docker-compose.dev.yml    # dev override: reload backend + Vite dev server
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
│       ├── main.py           # FastAPI app init, CORS, static files mount, /api/health
│       ├── config.py         # Settings (DATABASE_URL, GEMINI_API_KEY, model tiers, APP_TZ, WEBHOOK_TOKEN, STRAVA_CLIENT_ID/SECRET)
│       ├── database.py       # SQLModel engine, session dependency
│       ├── timeutils.py      # today()/day bounds in APP_TZ
│       ├── seed.py           # Default gym exercises seeder (idempotent)
│       ├── models/           # One module per domain [A13]
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
- `muscle_group`: `str` (chest, back, legs, shoulders, arms, core, full_body, cardio)
- `equipment`: `Optional[str]` (barbell, dumbbell, machine, bodyweight, cable)

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
- `set_order`: `int` (1, 2, 3…)
- `set_type`: `str` (`normal`, `warmup`, `drop`, `failure`; replaces `is_warmup`) **[A6]**
- `weight_kg`: `Optional[float]` (0 for bodyweight; null for pure time/distance sets)
- `reps`: `Optional[int]`
- `duration_s`: `Optional[int]` (planks, timed holds, rower) **[A6]**
- `distance_m`: `Optional[float]` (rower, sled, carries) **[A6]**
- `rpe`: `Optional[float]` (1.0–10.0)
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
- `steps`: `int`
- PK (`source`, `bucket_start`)

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
- `GET /api/exercises/{exercise_id}/last-performance`: **CRITICAL FOR GYM UI.** Returns the sets (`set_order`, `set_type`, `weight_kg`, `reps`, `duration_s`, `distance_m`, `rpe`) from the most recent completed workout containing this exercise. Used to pre-fill "ghost values".
- `GET /api/workouts`: recent workouts with aggregated total volume (`sum(weight_kg * reps)` over non-warmup sets) and set count.
- `GET /api/workouts/active`: the unfinished workout (if any) with its sets, for "Resume".
- `GET /api/workouts/templates`: for each distinct workout name (Chest tri, Back biceps, …), the most recent workout's ordered exercise list with set counts. Used by "Start from last …" **[E9]**. The client creates the new workout with its own UUID and pre-adds the exercises. Ghost values come from `/last-performance`.
- **Auto-finish [E9]:** an active workout with no newly completed set for **2 h** is closed by the scheduler sweep (every 10 min) and also on any read of `/api/workouts/active`. It gets `ended_at = last set's completed_at + 2 min` (or `started_at` if there are no sets) and `ended_by = auto_idle`. The UI shows "automaticky ukončeno" and lets the user adjust it.
- `PUT /api/workouts/{workout_id}`: create-or-update a workout (client UUID); may include nested sets **[A5]**.
- `PUT /api/workouts/{workout_id}/sets/{set_id}`: create-or-update a set (client UUID) **[A5]**.
- `DELETE /api/workouts/sets/{set_id}`: idempotent delete (204 even if already gone).
- `POST /api/workouts/import-strong-csv`: accepts a CSV exported from the Strong app (`Date, Workout Name, Duration, Exercise Name, Set Order, Weight, Reps, Distance, Seconds, Notes, Workout Notes, RPE`) **[A6]**. Behaviour is tuned to the user's real export (`data/imports/strong_workouts.csv`, analysed in review §G1):
  - Format: UTF-8, comma-delimited in the real export. Still sniff `,` vs `;` as a cheap safeguard. Query param `weight_unit=kg|lbs` (default `kg`; the real export is kg).
  - `Date` is **naive local time**, so localize it in `APP_TZ` before storing it as `timestamptz`.
  - `Weight 0.0` means bodyweight. On bodyweight exercises (Pull Up, Chest Dip) a weight > 0 is **added** load. `Distance`/`Seconds` of 0 and an empty `RPE` are stored as null. Numeric `Set Order` maps to `set_type=normal` (other markers map to set types if they ever appear).
  - `Duration` such as `"1h 8m"`, `"39m"`, `"1h"` or `"2 103h 34m"` (the thousands separator is a **non-breaking space**): strip spaces and NBSP before parsing. A duration **over 4 h** is treated as a workout never finished in Strong (62 % of the real export). For those, `ended_at = started_at + set_count × 3 min` (the user's empirical average) and `ended_by = import_estimate`, and the workout is listed in `warnings`.
  - **Exercise remap rules [E5]:** the user logged some movements under the closest Strong exercise and marked them with a sticky note on set 1. Each rule is `{strong_name, note_contains | null, map_to, muscle_group}` and applies to every set of that exercise in matching workouts (all workouts when `note_contains` is null). The marker note is then dropped. Default rules:
    - `Lat Pulldown (Machine)` → **Bent-over Pulldown** (back), all workouts (the note is on 41/41).
    - `Lat Pulldown - Underhand (Cable)` → **Kelso Shrug** (back), all workouts. This is an assumption: the note first appears on 2025-09-30, but loads continue seamlessly from the note-less workouts before it.
    - Rules can be overridden per import via an `exercise_map` JSON field.
  - Any other notes are kept in `WorkoutSet.notes`.
  - Missing exercises are auto-created. The seed already covers all 42 exercises of the real export with muscle groups, so this should only happen for future exercises. Workouts already imported are skipped (dedupe on `started_at` + `name`).
  - Returns `{workouts_created, workouts_skipped, sets_created, exercises_created, warnings[]}`.
  - Tests run against a small anonymized slice of the real export, covering an NBSP duration, an over-4 h duration, the remap rules and bodyweight sets.

### 6.4 Running & Marathon Plan (`/api/running`)
- `GET /api/running/activities`: cardio activities with calculated pace (min/km).
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
| Watch steps, sleep, resting HR | Samsung Health → Health Connect (on the Android phone paired with the watch) | Forwarder app on that phone → `POST /api/webhooks/health` **[E8]** |

**Strava [E10]**
- `GET /api/integrations/strava/connect` redirects to Strava authorize (scope `activity:read_all`). `GET /api/integrations/strava/callback` exchanges the code and stores it in `integration_tokens`. The redirect runs in the browser, so the tailnet hostname works as the callback domain and nothing is exposed publicly.
- `POST /api/integrations/strava/sync`: manual sync. The scheduler also syncs every 30 min, plus once when the app is opened.
  - It is incremental via `after=last_activity_start`. The first run backfills the full history page by page.
  - It refreshes the access token when it has expired. It maps each activity to `Activity` with `external_id = "strava:<id>"`, `source = strava`, and fetches details (calories) only for new activities.
  - It stays far below Strava's rate limits.
- `GET /api/integrations/status`: Strava connection + last sync, and the last payload received per webhook source.

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
1. Interval samples are distributed into **15-min buckets** (`step_buckets`) in proportion to their time overlap.
2. When **two or more sources have interval data** for the day: for each bucket, the merged value is **max over sources**, and the day total is the **sum** of those maxima. When both devices are carried, they count the same walking, so the max avoids double counting. When only one is carried or worn, that one fills the bucket, so steps taken with only the phone or only the watch are added together.
3. **Fallback** when a source has only a daily total: day total = **max** over the sources' daily totals. A source's bucket sum counts as its daily total.
4. The result is written to `DailyMetric.steps`. `GET /api/metrics/steps-breakdown?date=` returns per-source totals, the method used (`buckets` or `max_daily`), the merged total and the merged bucket series, so the number is explainable.

**Sleep [E8]:** sleep sessions are attributed to the **date of wake-up** (session end, in `APP_TZ`). `DailyMetric.sleep_hours` is the total of all sessions ending on that date, naps included. Samsung Health is the primary sleep source.

**Sender setup** (guides to be written in `docs/integrations/` during Phase 4, once the HTTPS URL exists):
- **iOS Shortcut [E6]:** one shortcut, triggered by several "Time of Day" personal automations set to run without asking (e.g. 12:00, 18:00 and 23:30), and also runnable by hand.
  - It uses `Find Health Samples` for Steps with Start Date today/yesterday and Source = this iPhone, so it doesn't re-send other apps' data.
  - It builds the JSON with each sample's start, end and count and runs `Get Contents of URL` (POST plus the token header).
  - Tailscale on-demand must be enabled on the iPhone.
- **Health Connect forwarder [E8]:** an app on the Android phone the watch is paired with. It must read Health Connect `StepsRecord` (with start/end) and `SleepSessionRecord` (resting HR optional), push them on a schedule in the background to a custom URL with a custom header, and work over Tailscale. **The app is chosen in Phase 1** (research task). Tailscale runs on that phone, and Samsung Health → Health Connect sync must be enabled.

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

---

## 7. Gemini API Implementation Reference (`backend/app/services/gemini_service.py`)

**IMPORTANT FOR AGENT:** follow this pattern using `google-genai`. Changes vs. the original sample: model tier from config **[A7]**, history from DB **[A10]**, typed tools + draft collection **[A9][E4]**, tool-call names from the AFC history.

```python
from google import genai
from google.genai import types
from sqlmodel import Session

from app.config import settings
from app.services.ai_tools import ToolContext, build_coach_tools

COACH_SYSTEM_INSTRUCTION = (
    "Jsi osobní silový a běžecký (maratonský) trenér a analytik. "
    "Máš přímý přístup do databáze uživatele pomocí nástrojů (tools). "
    "Před odpovědí na dotazy ohledně progresu, váhy, maker, stagnace ve fitku "
    "nebo běžeckého tréninku si VŽDY nejprve zavolej příslušné databázové nástroje. "
    "Pokud uživatel diktuje odjetou sérii nebo trénink, použij nástroj pro zápis do DB "
    "a stručně potvrď, co jsi uložil nebo co čeká na potvrzení. Odpovídej česky, věcně a prakticky."
)


def run_ai_coach(
    session: Session,
    user_message: str | None = None,
    audio_bytes: bytes | None = None,
    audio_mime_type: str | None = None,
    model_tier: str = "fast",
    history: list[types.Content] | None = None,
) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)

    # Tools are closures bound to the DB session; ctx collects drafts for the UI
    ctx = ToolContext(session=session)
    tools = build_coach_tools(ctx)

    parts: list[types.Part] = []
    if audio_bytes and audio_mime_type:
        parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime_type))
    parts.append(types.Part.from_text(text=user_message or "Zpracuj tuto hlasovou nahrávku z tréninku."))
    contents = [*(history or []), types.Content(role="user", parts=parts)]

    response = client.models.generate_content(
        model=settings.model_for(model_tier),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=COACH_SYSTEM_INSTRUCTION,
            tools=tools,
            temperature=0.2,
        ),
    )

    tool_calls_made = [
        part.function_call.name
        for content in (response.automatic_function_calling_history or [])
        for part in (content.parts or [])
        if part.function_call
    ]
    return {"reply": response.text, "tool_calls_made": tool_calls_made, "drafts": ctx.drafts}
```

### Required Coach Tools (`backend/app/services/ai_tools.py`)
Factory `build_coach_tools(ctx: ToolContext) -> list[Callable]` returning type-annotated, docstring-documented functions for Gemini automatic function calling. Structured arguments use **Pydantic models** (e.g. `SetInput`), not bare `dict` **[A9]** — verify that AFC handles `list[BaseModel]`; if not, declare those tools with explicit `FunctionDeclaration` schemas.

- `get_body_metrics_summary(days: int = 30) -> dict`: daily records, 7-day weight averages, average daily calories and macros (from `meal_logs` **[E1]**) for the last `days`.
- `get_muscle_group_volume(days: int = 30) -> dict`: total completed working sets and tonnage (weight × reps) grouped by `Exercise.muscle_group` over the last `days` (spots neglected muscle groups).
- `get_exercise_progression(exercise_name: str, weeks: int = 8) -> list[dict]`: finds the exercise via `pg_trgm` similarity + `unaccent` **[A4]**, returns workout dates, top set weight/reps, and estimated 1RM (`weight * (1 + reps/30)`) (detects plateaus).
- `get_running_and_marathon_context(days: int = 21) -> dict`: recent runs (distance, pace, avg HR) + upcoming 14 days of `TrainingPlanItem` + recent lower-body gym workouts (marathon fatigue vs. leg days).
- `log_workout_sets_from_ai(exercise_name: str, sets: list[SetInput], workout_id: str | None = None) -> dict`: matches the exercise, creates or attaches to today's active workout and saves the sets — or, per the hybrid flow **[E4]**, records a draft in `ctx.drafts` when the exercise match is fuzzy/new or numbers are implausible vs. last performance, and tells the model it awaits confirmation.
- `log_daily_metric_from_ai(weight_kg: float | None = None, steps: int | None = None, sleep_hours: float | None = None) -> dict`: upserts today's `DailyMetric` (today in `APP_TZ` **[A3]**).
- `log_quick_intake_from_ai(kcal: float, protein_g: float | None = None, carbs_g: float | None = None, fat_g: float | None = None) -> dict`: creates a quick-add meal item for today **[E1]** (detailed food logging belongs to the nutrition assistant in Phase 5 **[E2]**).

---

## 8. Frontend Requirements (Mobile-First PWA)
Clean, dark-mode default UI (Tailwind slate-900 / zinc-900 background) optimized for one-handed operation in the gym. Requires the HTTPS origin from `tailscale serve` for microphone and PWA install **[A2]**.

**Bottom Navigation Bar:** Dashboard (Home / Trends), Gym (Active Workout & History), Run (Activities & Marathon Plan), AI Coach (Chat & Voice Dictation). Phase 5 adds a 5th tab "Jídlo".

**Gym Logger Page (`GymLogger.tsx`) — key UX features:**
- **Start Workout / Resume Active Workout:** active workout state mirrored in `localStorage`; workouts and sets get client UUIDs and every change goes through the persisted mutation queue, so a dropped signal in a basement gym loses nothing and retries never duplicate **[A5]**.
- **Start from last … [E9]:** the start screen lists templates from `/api/workouts/templates` ("Chest tri", "Back biceps", …). Tapping one creates the workout with that exercise order pre-filled, and ghost values load per exercise. "Empty workout" remains available.
- **Auto-finish [E9]:** a forgotten workout closes itself after 2 h with no sets (see §6.3). The history marks it as "automaticky ukončeno" with an editable end time.
- **Ghost Values:** when an exercise is added, fetch `/api/exercises/{id}/last-performance` and show the previous session's weight & reps as placeholders / defaults.
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
- Alembic setup + initial migration enabling `pg_trgm` and `unaccent`.
- `docker-compose.yml` (db) + `docker-compose.dev.yml`; `.env.example`; pytest + ruff wired up.

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
- `ai_tools.py` (7 coach tools, Pydantic args, hybrid drafts), `gemini_service.py` (shared runner), `routers/ai_coach.py` (text + audio, conversation persistence), `services/audio.py`.

**Phase 3 — React frontend & PWA**
- Scaffold with Vite, React, TypeScript, Tailwind, lucide-react, TanStack Query (+ persist client), recharts.
- `Layout.tsx`, `RestTimer.tsx`, `VoiceRecorder.tsx`, `DraftCard.tsx` and the 4 pages; `vite-plugin-pwa` manifest.

**Phase 4 — Dockerization & deploy**
- Multi-stage `Dockerfile` (with ffmpeg), `docker-compose.yml` (db + app on port 8000 + backup), healthcheck on `/api/health`.
- FastAPI serves the built React `dist/` as an SPA fallback so refreshing any route works.
- `tailscale serve --bg 8000`; verify mic + PWA install on the iPhone over HTTPS.
- Integration setup with guides in `docs/integrations/`:
  - register the Strava API app and connect it;
  - build the iOS Shortcut and its automations;
  - install and configure the Health Connect forwarder plus Tailscale on the Android phone.

  Verify that data arrives from every source (Settings page).

**Phase 5 — Nutrition module**
- Per `docs/nutrition-module-spec.md`, including its "Amendments" section.

---

## 10. Commands & Verification
- Dev stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`
- Migrations: `docker compose exec app alembic revision --autogenerate -m "<msg>"`, `docker compose exec app alembic upgrade head`
- Tests / lint: `docker compose exec app pytest`, `docker compose exec app ruff check .`, frontend `npm run typecheck`
- Production: `docker compose up -d --build`; logs `docker compose logs -f app`
- Health: `curl -f http://localhost:8000/api/health && curl -f http://localhost:8000/api/exercises`
- HTTPS over the tailnet: `tailscale serve --bg 8000`
- Always verify container health and fix any startup tracebacks before finishing a phase.
