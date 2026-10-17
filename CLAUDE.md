Markdown
# Project Specification: Self-Hosted Fitness & Quantified-Self Hub

## 1. Project Overview
Build a full-stack, self-hosted, mobile-first Progressive Web App (PWA) for tracking personal health metrics, gym workouts (Strong app replacement), marathon running preparation, and an integrated AI Coach powered by the Google Gemini API.
The application will run inside Docker containers and be accessed primarily via smartphone and desktop over a private network (Tailscale).

---

## 2. Tech Stack & Strict Rules for the Coding Agent

### Backend
- **Language:** Python 3.12+
- **Framework:** FastAPI + Uvicorn
- **ORM & Validation:** SQLModel (combines SQLAlchemy 2.0 + Pydantic v2)
- **Database:** PostgreSQL 16 (via `psycopg` / `psycopg2-binary`)
- **AI SDK:** `google-genai` (CRITICAL: Use ONLY the new official `google-genai` package with `from google import genai`. DO NOT use the deprecated `google-generativeai` package!)
- **Data Processing:** `pandas` or Python built-in `csv` module (for Strong CSV imports)
- **Multipart/Audio handling:** `python-multipart`

### Frontend
- **Framework:** React 18+ with Vite and TypeScript
- **Styling:** Tailwind CSS + `lucide-react` icons
- **State & Data Fetching:** `@tanstack/react-query` (TanStack Query v5) with optimistic updates and `localStorage` persistence for active workouts
- **Charts:** `recharts`
- **Routing:** `react-router-dom`
- **PWA Support:** `vite-plugin-pwa` (configured for standalone mobile screen display)

### Infrastructure
- **Containerization:** Docker & `docker-compose.yml`
- **Services:**
  1. `db`: `postgres:16-alpine` with persistent volume
  2. `app`: Multi-stage Docker build (Stage 1 builds React static files via Node, Stage 2 runs Python FastAPI serving `/api/*` and mounting the built React SPA at `/`)

---

## 3. Directory Structure

```text
fitness-hub/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── SPEC.md
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app init, CORS, static files mount
│   │   ├── config.py            # Env vars (DATABASE_URL, GEMINI_API_KEY)
│   │   ├── database.py          # SQLModel engine, session dependency, init_db
│   │   ├── models.py            # All SQLModel database tables & schemas
│   │   ├── seed.py              # Default gym exercises seeder
│   │   ├── routers/
│   │   │   ├── metrics.py       # Daily weight, calories, macros, steps
│   │   │   ├── workouts.py      # Gym workouts, sets, ghost values, Strong CSV import
│   │   │   ├── running.py       # Cardio activities & marathon training plan
│   │   │   ├── webhooks.py      # Ingestion endpoints for mobile health exports
│   │   │   └── ai_coach.py      # Gemini chat, voice workout logging, analysis
│   │   └── services/
│   │       ├── gemini_service.py # google-genai client & tool execution logic
│   │       └── ai_tools.py       # Python functions exposed to Gemini as Tools
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   └── client.ts        # Fetch/Axios wrapper & TanStack Query keys
        ├── components/
        │   ├── Layout.tsx       # Mobile bottom nav + desktop sidebar
        │   ├── RestTimer.tsx    # Floating countdown timer for gym sets
        │   └── VoiceRecorder.tsx # MediaRecorder button sending audio to Gemini
        └── pages/
            ├── Dashboard.tsx    # Weight 7d avg chart, macros, weekly summary
            ├── GymLogger.tsx    # Active workout UI, ghost values, +/- steppers
            ├── RunningPlan.tsx  # Marathon schedule vs completed runs
            └── AiCoach.tsx      # Chat UI + Voice workout dictation
4. Database Schema (backend/app/models.py)
Implement the following SQLModel tables:

4.1 DailyMetric (Table: daily_metrics)
date: datetime.date (Primary Key)

weight_kg: Optional[float]

calories_in: Optional[int]

calories_out: Optional[int]

protein_g: Optional[int]

carbs_g: Optional[int]

fat_g: Optional[int]

steps: Optional[int]

sleep_hours: Optional[float]

notes: Optional[str]

4.2 Exercise (Table: exercises)
id: Optional[int] (Primary Key)

name: str (Unique, Indexed, e.g., "Bench Press (Barbell)")

muscle_group: str (Enum/String: chest, back, legs, shoulders, arms, core, full_body, cardio)

equipment: Optional[str] (e.g., barbell, dumbbell, machine, bodyweight, cable)

4.3 Workout (Table: workouts)
id: Optional[int] (Primary Key)

name: str (e.g., "Push Day", "Full Body")

started_at: datetime.datetime (Indexed)

ended_at: Optional[datetime.datetime]

notes: Optional[str]

4.4 WorkoutSet (Table: workout_sets)
id: Optional[int] (Primary Key)

workout_id: int (ForeignKey workouts.id, ondelete CASCADE)

exercise_id: int (ForeignKey exercises.id)

set_order: int (1, 2, 3...)

weight_kg: float

reps: int

rpe: Optional[float] (Rate of Perceived Exertion, 1.0 - 10.0)

is_warmup: bool (default False)

completed: bool (default True)

4.5 Activity (Table: activities - Running & Cardio)
id: Optional[int] (Primary Key)

external_id: Optional[str] (Unique, Indexed - for deduplication from Strava/Watches)

source: str (default "manual", e.g., "strava", "samsung_health")

start_time: datetime.datetime (Indexed)

activity_type: str (e.g., "Run", "Walk", "Ride")

distance_meters: float

duration_seconds: int

avg_hr: Optional[int]

max_hr: Optional[int]

calories: Optional[int]

notes: Optional[str]

4.6 TrainingPlanItem (Table: training_plan_items - Marathon Prep)
id: Optional[int] (Primary Key)

planned_date: datetime.date (Indexed)

title: str (e.g., "Long Run Z2", "Tempo Intervals 4x2km")

target_distance_meters: Optional[float]

target_pace_sec_per_km: Optional[int]

description: Optional[str]

completed_activity_id: Optional[int] (ForeignKey activities.id, nullable)

5. Backend API Specification
5.1 Metrics (/api/metrics)
GET /api/metrics?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD: Returns daily metrics + calculated 7-day rolling average for weight_kg and calories_in.

POST /api/metrics: Upserts (creates or updates) a DailyMetric record for a given date. Only non-null fields in the payload should overwrite existing fields.

5.2 Gym & Workouts (/api/workouts, /api/exercises)
GET /api/exercises: List all exercises. (Seed 30 common gym exercises on DB init).

POST /api/exercises: Create a custom exercise.

GET /api/exercises/{exercise_id}/last-performance: CRITICAL FOR GYM UI. Returns the sets (set_order, weight_kg, reps, rpe) from the most recent completed workout containing this exercise. Used to pre-fill "ghost values" in the UI.

GET /api/workouts: List recent workouts with aggregated total volume (sum(weight_kg * reps)) and set count.

POST /api/workouts: Create a new workout (can accept nested sets or sets can be added incrementally).

POST /api/workouts/{workout_id}/sets: Add/update a set in an active workout.

DELETE /api/workouts/sets/{set_id}: Delete a set.

POST /api/workouts/import-strong-csv: Accepts a CSV file exported from the Strong app (Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE), auto-creates missing exercises, and imports historical workouts and sets.

5.3 Running & Marathon Plan (/api/running)
GET /api/running/activities: List cardio activities with calculated pace (min/km).

POST /api/running/activities: Log a run manually or via webhook.

GET /api/running/plan?start_date=...&end_date=...: Get planned marathon workouts alongside linked actual activities.

POST /api/running/plan: Create/update a planned run.

5.4 AI Coach & Voice Dictation (/api/ai)
POST /api/ai/chat:

Accepts message: str, model: str = "gemini-2.5-flash" (or "gemini-2.5-pro"), and optional history: list.

Executes Gemini with Function Calling tools connected to the database.

Returns reply: str and tool_calls_made: list[str].

POST /api/ai/voice-workout:

Accepts UploadFile (audio .webm, .mp3, .wav, .m4a recorded on mobile) OR text: str, plus workout_id: Optional[int].

Uses Gemini multimodal input to parse spoken Czech/English workout dictation (e.g., "Bench press první série 80 kilo 10 opakování, druhá 85 kilo 8 opakování, RPE 8").

Calls the DB tool to log the sets (or returns structured JSON of parsed sets for 1-click confirmation).

6. Gemini API Implementation Reference (backend/app/services/gemini_service.py)
IMPORTANT FOR AGENT: Follow this exact pattern using google-genai.

Python
import os
from google import genai
from google.genai import types
from sqlmodel import Session
from app.services.ai_tools import build_db_tools

def run_ai_coach(
    session: Session,
    user_message: str | None = None,
    audio_bytes: bytes | None = None,
    audio_mime_type: str | None = None,
    model_name: str = "gemini-2.5-flash",
) -> dict:
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    # Bind current DB session to tool functions
    tools = build_db_tools(session)
    
    system_instruction = (
        "Jsi osobní silový a běžecký (maratonský) trenér a analytik. "
        "Máš přímý přístup do databáze uživatele pomocí nástrojů (tools). "
        "Před odpovědí na dotazy ohledně progresu, váhy, maker, stagnace ve fitku "
        "nebo běžeckého tréninku si VŽDY nejprve zavolej příslušné databázové nástroje. "
        "Pokud uživatel diktuje odjetou sérii nebo trénink, použij nástroj pro zápis do DB "
        "a stručně potvrď, co jsi uložil. Odpovídej česky, věcně a prakticky."
    )

    contents = []
    if audio_bytes and audio_mime_type:
        contents.append(
            types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime_type)
        )
    if user_message:
        contents.append(user_message)
    elif audio_bytes:
        contents.append("Zpracuj tuto hlasovou nahrávku z tréninku.")

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.2,
        ),
    )

    return {
        "reply": response.text,
    }
Required AI Tools (backend/app/services/ai_tools.py)
Create a factory function build_db_tools(session: Session) -> list[Callable] returning properly type-annotated and docstring-documented Python functions so Gemini automatic function calling can inspect them:

get_body_metrics_summary(days: int = 30) -> dict: Returns daily records, 7-day weight averages, average daily calories and macros for the last days.

get_muscle_group_volume(days: int = 30) -> dict: Aggregates total completed working sets and tonnage (weight * reps) grouped by Exercise.muscle_group over the last days. (Allows AI to spot neglected muscle groups like shoulders or legs).

get_exercise_progression(exercise_name: str, weeks: int = 8) -> list[dict]: Searches exercise by ILIKE, returns workout dates, top set weight/reps, and estimated 1RM (weight * (1 + reps/30)). (Allows AI to detect plateaus/stagnation).

get_running_and_marathon_context(days: int = 21) -> dict: Returns recent running activities (distance, pace, avg HR) + upcoming 14 days of TrainingPlanItem + recent lower-body gym workouts. (Allows AI to advise on marathon fatigue vs leg days).

log_workout_sets_from_ai(exercise_name: str, sets: list[dict], workout_id: int | None = None) -> dict: Finds or fuzzy-matches the exercise, creates or attaches to today's active Workout, and inserts WorkoutSet rows (weight_kg, reps, rpe).

log_daily_metric_from_ai(weight_kg: float | None = None, calories_in: int | None = None, protein_g: int | None = None, carbs_g: int | None = None, fat_g: int | None = None, steps: int | None = None) -> dict: Upserts today's DailyMetric.

7. Frontend Requirements (Mobile-First PWA)
Design a clean, dark-mode default UI (Tailwind slate-900 / zinc-900 background) optimized for one-handed operation in the gym.

Bottom Navigation Bar:

Dashboard (Home / Trends)

Gym (Active Workout & History)

Run (Activities & Marathon Plan)

AI Coach (Chat & Voice Dictation)

Gym Logger Page (GymLogger.tsx) - Key UX Features:

Start Workout / Resume Active Workout: Active workout state must be mirrored in localStorage so if mobile signal drops in a basement gym, zero data is lost.

Ghost Values: When an exercise is added to the workout, automatically fetch /api/exercises/{id}/last-performance and display previous session's weight & reps as placeholders / default values.

Quick Stepper Controls: Next to Weight (kg) and Reps inputs, provide -2.5 / +2.5 buttons for weight and -1 / +1 buttons for reps so the user rarely needs to open the mobile keyboard.

1-Tap Complete & Rest Timer: Tapping the checkmark button marks the set completed, sends an optimistic mutation to the backend, and automatically starts the floating RestTimer component (configurable 60s / 90s / 120s / 180s countdown with visual progress bar).

Voice Dictation Shortcut: Include a floating microphone button (VoiceRecorder.tsx) right inside the active workout screen so the user can dictate sets hands-free.

Dashboard Page (Dashboard.tsx):

Quick input card at the top: "Today's Weight (kg)" & "Calories In (kcal)" with instant save.

Chart 1 (Recharts ComposedChart): Daily weight (scatter/dots) overlaid with a smooth 7-day rolling average line + daily caloric intake bars.

Chart 2: Weekly gym volume by muscle group & weekly running mileage (km).

AI Coach Page (AiCoach.tsx):

Model selector toggle at top: Flash (Rychlý zápis & dotazy) vs Pro (Hloubková analýza).

Quick prompt chips:

"Analyzuj moji stagnaci a objem partií za poslední měsíc"

"Zhodnoť můj běžecký plán na tento týden vůči únavě z fitka"

Text input + Hold/Tap-to-record Audio button using browser navigator.mediaDevices.getUserMedia and MediaRecorder.

8. Implementation Phases (Instructions for Agent)
Execute the implementation in these exact phases, verifying each before moving on:

Phase 1: Backend Core & Database

Create backend/requirements.txt, config.py, database.py, models.py, and seed.py.

Implement CRUD routers for metrics.py, workouts.py (including /last-performance and Strong CSV importer), running.py, and webhooks.py.

Wire up main.py with automatic DB table creation and exercise seeding on startup.

Phase 2: Gemini AI Service & Tools

Implement backend/app/services/ai_tools.py with all 6 database inspection/mutation tools.

Implement backend/app/services/gemini_service.py and routers/ai_coach.py supporting both text and audio uploads.

Phase 3: React Frontend & PWA

Scaffold frontend/ with Vite, React, TypeScript, Tailwind CSS, lucide-react, @tanstack/react-query, and recharts.

Build Layout.tsx, RestTimer.tsx, VoiceRecorder.tsx, and the 4 core pages (Dashboard, GymLogger, RunningPlan, AiCoach).

Configure vite-plugin-pwa manifest for mobile installation.

Phase 4: Dockerization

Create multi-stage Dockerfile and docker-compose.yml (PostgreSQL 16 + App on port 8000) and .env.example.

Ensure FastAPI serves the built React dist/ folder as a SPA fallback so refreshing any route works seamlessly.


## 9. Agent Commands & Verification
- Build and start services: `docker compose up -d --build`
- Check backend logs: `docker compose logs -f app`
- Test API health: `curl -f http://localhost:8000/api/exercises || exit 1`
- Always verify container health and fix any startup tracebacks before finishing a phase.
