# Plan review — 2026-10-17

Scope: the core spec (`CLAUDE.md`, commit `d93d650`) and the nutrition module spec
(`docs/nutrition-module-spec.md`). The repo has no code yet, only specs.

**Status:** decisions E0, E1, E2 and E4 made on 2026-10-17 and applied to `docs/SPEC.md` and to the nutrition spec's Amendments. E3 and the info items in §F are still open (tracked in `docs/PROGRESS.md`).

---

## Evidence: live API checks (2026-10-17)

These checks back the findings in §C.

| Check | Result |
|---|---|
| USDA search, SR Legacy, "chicken thigh meat only raw" | Top hit fdcId 173627, correct. Nutrients are keyed by `nutrientId` (1003, 1004, 1008, …), and `nutrientNumber` is the old 203/204/208 scheme. Saturated fat = **1258**, sugars = 2000, ω-3: **1404** ALA, **1278** EPA, **1272** DHA, **1280** DPA. ω-6: **1316** LA (18:2 n-6), 1269 (18:2 undifferentiated), 1271 (20:4). Folate DFE = **1190**, Vit D µg = 1114 (1110 is IU). |
| USDA search, Foundation only, "potatoes boiled" | Returned *kale, frozen, boiled* and *potato flour*. Foundation is small (hundreds of foods) and ranks poorly. Foundation records use **1063 "Sugars, Total"** instead of 2000. Potato flour has energy only as **2047/2048**, with no 1008. Kale has **no fiber** record. |
| OFF legacy `cz.openfoodfacts.org/cgi/search.pl` "skyr madeta" | 0 hits. On `world.`, the same endpoint returned an HTML "Page temporarily unavailable". |
| OFF new search `search.openfoodfacts.org/search?q=madeta skyr` | Returns JSON, but relevance is poor: Madeta žervé, a Canadian skyr, Madeta tvaroh. |
| OFF barcode `api/v2/product/8593803614014.json` | Madeta Tvaroh polotučný came back with full macros per 100 g and **no fiber key**: the value is absent, not 0. `energy_100g` is in **kJ**, so read `energy-kcal_100g`. |
| Local machine | Docker 29.8 + Compose v5.5, Tailscale and Python 3.14 are installed. **Node is not installed.** `.env` `DATABASE_URL` uses the scheme `postgresql://`, host `db`. |

---

## A. Core plan: must-fix

- **A1. CLAUDE.md is broken and in the wrong role.** The ```` ```text ```` fence in §3 is never closed, so §4–§9 render as one code block. The §4.x and §5.x headings have no `#`, the Python sample in §6 has no fence, and the file starts with a stray "Markdown" line. The file also references a `SPEC.md` that doesn't exist. CLAUDE.md loads into every agent session, so it should stay short.
  → Split it into `CLAUDE.md` (rules, stack, commands, conventions, pointer to progress), `docs/SPEC.md` (core spec, fixed), `docs/nutrition-module-spec.md` and `docs/PROGRESS.md` (phase checklist and session log).
- **A2. HTTPS over Tailscale.** Microphone access (`getUserMedia`), camera access (barcode scanning) and the service worker behind PWA install all require a secure context. `http://<tailscale-ip>:8000` is not one, so voice dictation and PWA install fail on the phone.
  → `tailscale serve --bg 8000` gives `https://<host>.<tailnet>.ts.net` with a real certificate. It needs no code; it just has to be in the deploy docs.
- **A3. Timezone.** Containers run in UTC, so "today" in the AI tools and in meal or metric logging lands on the wrong date after midnight in Prague.
  → Use `timestamptz` everywhere, add `APP_TZ=Europe/Prague`, and compute every "today" or date bucket in that zone.
- **A4. Migrations from day one.** `create_all` creates missing tables but never alters existing ones. After the Strong and KT imports there will be real data, and the nutrition module already needs schema changes (see B1).
  → Use Alembic. Its first migration also enables the `pg_trgm` and `unaccent` Postgres extensions, which give fuzzy, diacritics-insensitive matching for exercises ("bench" → "Bench Press (Barbell)") and foods ("kureci" → "kuřecí").
- **A5. Idempotent offline writes.** Optimistic mutations retried after the basement signal comes back will insert duplicate sets. A workout started offline also has no server id to attach sets to.
  → Clients generate UUIDs for workouts, sets and meal entries, the server upserts by UUID, and queued mutations persist through TanStack Query `persistQueryClient` and resume when the connection returns.
- **A6. Strong CSV realities.** The delimiter and units depend on the export's locale and app settings. Timed and distance exercises (plank, rower) use the `Seconds`/`Distance` columns, which `WorkoutSet` has no fields for. Re-importing the same file must not duplicate data.
  → Add `distance_m`, `duration_s` and `set_type` (normal/warmup/drop/failure, replacing `is_warmup`) to `WorkoutSet`, and make the importer detect delimiter and units and dedupe on (started_at, workout name). **I need a real export file to build against.**
- **A7. Gemini model ids are hardcoded** (`gemini-2.5-flash` / `-pro`). Newer Gemini 3.x models exist, and the 2.5 models may already be deprecated.
  → Use env config (`GEMINI_MODEL_FAST`, `GEMINI_MODEL_SMART`) and check the live model list at implementation time.
- **A8. Audio formats.** Android Chrome's MediaRecorder produces `audio/webm;codecs=opus` and iOS Safari produces `audio/mp4`. Neither is on Gemini's documented audio list (wav, mp3, aiff, aac, ogg, flac). They may still work.
  → Test first. Ship `ffmpeg` in the image and transcode to ogg or flac if needed.
- **A9. Tool schemas.** `sets: list[dict]` gives Gemini automatic function calling an untyped schema.
  → Use Pydantic models (`SetInput`, `MealItemInput`) for tool arguments, and read `tool_calls_made` from `response.automatic_function_calling_history`.
- **A10. Chat history is accepted but ignored** by the reference `run_ai_coach`. Multi-turn corrections ("ne, bylo to 150 g") need it.
  → Store conversations server-side (`chat_messages`), so a chat started on the phone continues on desktop.
- **A11. Backups.** Years of personal data sit in a single Docker volume.
  → Run a daily `pg_dump` to `./data/backups` with rotation (the `data/` folder is already gitignored).
- **A12. Dev loop.** Iterating only through the multi-stage build is slow.
  → Run Postgres in Docker, `uvicorn --reload` and the Vite dev server with an `/api` proxy, and use the multi-stage build only for deploy. Node is missing locally, so either install it or run Vite in a container.
- **A13. Small items.**
  - Normalize `DATABASE_URL` to `postgresql+psycopg://` (psycopg 3) in `config.py`.
  - Split `models.py` into a `models/` package (body, gym, running, nutrition, chat).
  - Add pytest with recorded fixtures for USDA, OFF and Gemini, plus ruff and `tsc --noEmit`.
  - Put a shared-secret header on the webhook endpoints.

## B. Nutrition module ↔ core integration

- **B1. Double source of truth for intake.** `DailyMetric.calories_in/protein_g/carbs_g/fat_g` overlaps with `meal_logs`. The integer and float types also differ.
  → *Decision E1.*
- **B2. ORM and database.** The nutrition spec says "SQLAlchemy, PostgreSQL or SQLite".
  → Use SQLModel (JSONB through `sa_column`) and **PostgreSQL only**, because the design needs JSONB, `pg_trgm` and `unaccent`.
- **B3. One assistant or two.**
  → *Decision E2.*
- **B4. Voice input.** Drop the Web Speech API (no Firefox support, flaky in an iOS PWA, needs a network anyway).
  → Reuse the existing `VoiceRecorder` → Gemini audio path. Gemini also fixes STT slips like "britský maso" from context.
- **B5. Layout.**
  - Backend: `services/nutrition/{usda.py, off.py, resolver.py, kt_import.py, nutrients.py}` and `routers/nutrition.py`.
  - Frontend: `pages/Nutrition.tsx` and `pages/FoodDatabase.tsx`, plus a 5th bottom-nav tab ("Jídlo").
- **B6. Phase order.** Core phases 1–4 come first and nutrition becomes Phase 5. Anything nutrition depends on (B1 schema, Alembic, extensions, unified assistant) is decided **now** to avoid rework.

## C. Nutrition module: data quality and missing pieces

- **C1. Unknown is not zero.** The spec defaults micronutrients and secondary macros to `0.0`, but OFF and KT foods mostly have no micronutrients, and some have no fiber. Daily totals would then show "40 % iron" when half the day's food simply has no data.
  → `kcal/protein/carbs/fat` are required. `sugar/saturated_fat/fiber/salt` are nullable. The micronutrient JSON holds **only known keys**. The daily summary reports **coverage** (the share of the day's kcal that has data for each nutrient), and the UI shows it.
- **C2. USDA mapping fixes** (verified in the evidence table):
  - Map by `nutrientId` only.
  - Add saturated fat `1258`.
  - Sugars: `2000`, falling back to `1063`. Energy: `1008`, falling back to `2048` and then `2047`. Carbs: `1005`, falling back to `1050` ("by summation").
  - Salt: `sodium_mg × 2.5 / 1000`, because USDA has no salt field.
  - ω-3 = `1404` (or `1270` when 1404 is absent) + `1278` + `1272` + `1280`. ω-6 = `1316` (or `1269`) + `1271`. Both are approximations.
  - Use folate **DFE** `1190` for RDI, since DRIs are defined in DFE; keep `1177` as the fallback.
- **C3. USDA strategy.** API search quality is mediocre and `DEMO_KEY` is rate-limited.
  → *Decision E3.* Option: bulk-seed SR Legacy + Foundation locally (about 8k foods, public domain, only mapped nutrients stored). Searching `name_en` with `pg_trgm` locally then works offline and with no limits. Either way, Gemini picks the best candidate from about the top 10, with a confidence score.
- **C4. OFF strategy.** Text search is unreliable for Czech products and barcode lookup works well.
  → Use **barcode first**: add EAN scanning to the PWA (BarcodeDetector on Android Chrome, `@zxing/browser` as fallback, HTTPS required, see A2). Text search becomes best-effort through the new `search.openfoodfacts.org`. Send a custom User-Agent, respect roughly 10 searches/min, and read `energy-kcal_100g`, never `energy_100g` (kJ).
- **C5. Web-grounded fallback values** (Google Search on kosik/rohlik/KT) get their own source value `web_estimate` and a low-confidence badge, and are never silently mixed with lab data. Grounding runs as a separate, isolated Gemini call, not in the same request as function tools, because combining them isn't supported on all models.
- **C6. Alias poisoning.** If a wrong USDA pick is saved automatically as an alias, it stays wrong for every future log, and nothing flags it.
  → *Decision E4.* Draft card → confirm. An alias is only created or upgraded on confirmation. This matches the "1-click confirmation" already planned for voice workouts.
- **C7. Czech morphology.** "kuřecích stehen" and "kuřecí stehno" are different strings, so exact aliases on the raw user phrase rarely repeat.
  → Key aliases mainly on the LLM's canonical nominative name, normalized with `unaccent` and lowercase. Also put the user's ~150 most-used foods (id + name) into the prompt, so Gemini returns `food_id` directly for known foods and most daily logs never reach the resolver.
- **C8. Snapshots are inconsistent.** Only kcal and P/C/F are snapshotted, while micronutrients are computed live.
  → Compute everything live from `foods` (single user: fixing a wrong food should fix its history). `meal_log_items.food_id` becomes nullable and gets optional manual nutrient fields for quick-add items ("500 kcal").
- **C9. Missing for daily use:**
  - **Recipes and batch cooking.** "Uvařil jsem 2 kg guláše, snědl 400 g": a composite food made of raw ingredient weights plus a cooked yield weight, with per-100 g values computed automatically. This also handles weighing raw vs cooked.
  - **Portions table** `food_portions(food_id, label, grams)`: "1 rohlík = 43 g", "1 kelímek = 140 g". Seed it from USDA `foodPortions` and OFF `serving_quantity`. The hardcoded unit list in the prompt moves into the DB, and LLM guesses become the fallback.
  - **Targets and RDI.** % RDI needs a reference: a profile (sex, birth year, height, with weight taken from metrics), an EU NRV or DRI table, and kcal/macro targets that can differ between training and rest days (carbs before long runs).
  - **Favourites, recent foods, "copy yesterday's breakfast".**
  - Later: **adaptive TDEE** from the weight trend plus intake (like MacroFactor), exposed as an AI coach tool.
- **C10. KalorickéTabulky.** There is no official API. A login- or cookie-based scraper can break at any time and may conflict with KT's terms.
  → Build file import first and keep the scraper as an isolated optional adapter. KT foods carry macros only, so they link to a USDA base food for micronutrients (the spec's "hybrid enrichment", generalized as `micros_reference_food_id`). **I need to know which export the user has.**
- **C11. Worth checking later:** NutriDatabáze.cz, the Czech national food composition database, has Czech-named foods with micronutrients (rohlík, tvaroh, eidam) that USDA covers poorly. Licensing and export terms are unverified.

## D. Optional core improvements

- **D1.** Add `Exercise.secondary_muscles` so volume analysis counts bench press toward triceps and front delts.
- **D2.** Add a `Race` goal (date, target time). Give the AI a tool that generates the marathon plan into `TrainingPlanItem`, and auto-link activities to plan items by date and type.
- **D3.** Make ghost values also return a suggested next set (progressive overload hint).
- **D4.** Webhooks depend on the devices in use (see F2).

## E. Decisions

| # | Question | Recommendation | Answer |
|---|---|---|---|
| E0 | Apply the A-list fixes and restructure the docs? | Yes | **Yes, apply all** (2026-10-17) |
| E1 | Source of truth for intake | `meal_logs` only. `DailyMetric` drops the macro fields, and the dashboard's quick "kcal" input becomes a quick-add meal item. The minimal meal tables ship in Phase 1. | **As recommended** (2026-10-17) |
| E2 | One assistant or two | One unified Gemini assistant with all tools. The Coach page and the quick food logger are two entry points into it. | **Two separate assistants** (2026-10-17). They share the Gemini runner but have separate prompts, toolsets and conversations; the coach only reads intake totals. |
| E3 | USDA strategy | Bulk-seed SR Legacy + Foundation locally | *pending, decide before Phase 5* |
| E4 | Meal logging flow | Hybrid: auto-save when every item resolves through a confirmed alias or food, otherwise show a draft card to confirm | **Hybrid, as recommended** (2026-10-17). Applies to dictated workouts as well. |
| E5 | Meaning of the Strong sticky notes | — | **They are different exercises.** The user picked the closest Strong exercise and noted the real one. Remap `Lat Pulldown (Machine)` → Bent-over Pulldown and `Lat Pulldown - Underhand (Cable)` → Kelso Shrug for **all** workouts. Confirmed by the user afterwards (O1), and the March 2026 low-rep sets stay the same movement. |
| E6 | Apple Health path | iOS Shortcut | **iOS Shortcut** |
| E7 | Steps from iPhone + watch | Max per day | **The user's rule:** combine by time (15-min buckets: max per bucket, summed over the day), with the daily max as fallback when no time data exists. |
| E8 | Samsung Health path | — | **Live sync via Health Connect** (forwarder app on the Android phone, chosen in Phase 1) |
| E9 | Gym extras | — | **Auto-finish workouts + "Start from last …" templates.** KT weight early: no, it stays in Phase 5. |
| E10 | Strava | OAuth + polling (no public webhook) | Proposed together with the answers; no objection |

## F. Info needed from the user

- **F1.** A Strong CSV export: drop it in `data/` (gitignored).
- **F2.** Phone (Android or iPhone) and watch or platform (Garmin, Samsung, Strava, Apple Health?). This drives the webhook design.
- **F3.** The KalorickéTabulky situation: Premium or not, and whether there's an export (format?) or a GDPR data request.
- **F4.** Single user only? Assumed yes, so there is no `user_id` anywhere.
- **F5.** Should progress be committed to git as we go, or left uncommitted?

---

## G. Follow-up: user answers to F1–F5 (2026-10-17)

- **F1:** Strong export received → `data/imports/strong_workouts.csv` (gitignored). Analysis in G1.
- **F2:** iPhone 16 Pro (main phone, PWA) and Galaxy Watch 6 Classic (non-LTE). Runs go to Strava; Samsung Health has the watch steps, Apple Health has the phone steps. Proposals in G3.
- **F3:** KalorickéTabulky, non-Premium. Data loads through the **`tomasvotava/kaloricketabulky`** Python SDK. Analysis in G2.
- **F4:** Single user **for now**, might change later. So no `user_id` yet. Keep data access in service functions so adding a user filter later stays local. `tailscale serve` already sends `Tailscale-User-Login`/`Tailscale-User-Name` headers, so multi-user auth can be added cheaply later.
- **F5:** Commit as we go. Work happens on the `dev` branch and `master` stays at the initial spec until merged.

### G1. Strong CSV, what the real export shows
- The format matches the spec header. It is **comma-delimited, UTF-8, no BOM**, 2,361 set rows, 123 workouts (2025-08-07 → 2026-10-17), 42 distinct exercises. A workout is uniquely identified by its `Date`. Timestamps are **naive local time**, so interpret them in `APP_TZ`.
- Weights are in **kg**. Max: bench 110, squat 110, leg press 180. `0.0` means bodyweight. Pull Up goes up to 25, which is **added** load on bodyweight exercises.
- `RPE` is empty in every row and `Distance`/`Seconds` are always 0, so the importer stores 0 as null. `Set Order` is numeric 1–5 only, with no warm-up or drop markers.
- **Durations are unreliable.** 76 of 123 workouts (62 %) run longer than 4 h because they were never finished in Strong; the median is 22 h and the maximum is `2 103h 34m`, written with a **non-breaking space** as the thousands separator. The importer handles this as follows:
  - It strips spaces and NBSPs before parsing.
  - For durations over 4 h it sets `ended_at = started_at + sets × 3 min`. Three minutes per set is the empirical average from the user's 46 normal workouts. These workouts are reported in `warnings`.
- **Sticky exercise notes** appear on set 1 of every occurrence:
  - "Takovej ten bent over pulldown": on all 41 *Lat Pulldown (Machine)* workouts.
  - "Kelso shrug": on 29 of 40 *Lat Pulldown - Underhand (Cable)* workouts.

  They may mean the exercise was really a different movement, so they need user input (G4). Either way the note needs a place in the schema.
- Exercises include customs ("Dragon Fly 🐉", "Chest Fly", "Triceps Extension", "T Bar Row", "Leg Press"). The seed should cover all 42 with muscle groups so the import never creates exercises with an unknown muscle group.
- Workout names reflect a split (Chest tri, Back biceps, Legs 2 / legs, Shoulders). The spec has no workout templates, which makes "repeat last *Chest tri*" a natural Strong-replacement feature.

### G2. KalorickéTabulky SDK (`kaloricketabulky-sdk` on PyPI, MIT, v0.1.1 alpha, Python ≥ 3.12, httpx + pydantic, async, read-only)
- `client.login(email, password)` uses session cookies, which can expire, so re-login when that happens. `get_diary(day)` returns meals (`times`) with foodstuffs and activities, plus day totals. `get_snapshot(SnapshotType.WEIGHT, from, to)` returns **weight history**.
- The SDK has no retry logic, and its author asks for slow, infrequent requests. The import is therefore **throttled** (about 1 request per 2 s), **resumable** (it records the last imported day) and runs as a background job. Credentials come from `.env` (`KALORICKETABULKY_EMAIL` / `_PASSWORD`) and are never stored in the DB.
- Diary foodstuff fields:
  - `guidType` is a stable food id → `foods.external_id`.
  - `title` → `name_cs`; `url` is the food page slug.
  - `unit` is a free-text amount, e.g. `"2 x kus (90 g)"` or `"0,6 x porce (50 g)"`. Grams are parsed from the parentheses. **Whether that number is per unit or the total for the entry must be verified on real data.**
  - Nutrient values appear to be **per entry**, so per-100 g = value / grams × 100. This needs the same verification.
  - KT provides energy, protein, carbs, fat, fiber, sugar, salt, sat/trans/mono/poly fat, cholesterol, **sodium and calcium**, water, alcohol and phe. That is more than macros only.
- KT meal slots are Snídaně, Dopolední svačina, Oběd, Odpolední svačina, Večeře, **Druhá večeře**. Add `second_dinner` to `meal_type`.
- Diary `activities` (with steps and energy) are not imported, because Strava and the health sources own activity data.
- The SDK fixtures are anonymized with random values, so build tests from one real, anonymized diary day.

### G3. Device data ingestion, proposals
- **Strava (runs):** OAuth app plus **polling**: on app open, every ~30 min, and a "Sync now" button. Strava's push webhooks need a public HTTPS callback (Tailscale Funnel), which a private setup doesn't need. The OAuth redirect happens in the browser, so the tailnet hostname works as the callback domain. A one-time history backfill is paginated. `Activity.external_id = "strava:<id>"`. Strava is the **only** source for activities, so `samsung_health` activities are not ingested and won't duplicate runs.
- **Apple Health (iPhone steps):** either a free iOS Shortcuts personal automation that runs daily and posts to `POST /api/webhooks/health`, or the paid Health Auto Export app with scheduled REST pushes, more metrics and history backfill. Tailscale must be on (on-demand) on the iPhone.
- **Samsung Health (watch steps, sleep):** there is no cloud API. Samsung Health syncs to Health Connect on the **Android phone the watch is paired with** (a Galaxy Watch 6 can't pair with an iPhone). A forwarder app on that device posts to the same webhook, and Samsung Health's "Download personal data" CSV export gives a one-off history backfill. The forwarder app is to be chosen at implementation time, depending on that device.
- **Steps from two sources double count.** Store per source and per day in `daily_source_metrics(date, source, metric, value)`, and use **max across sources** as the day's value: the watch and phone count the same walks, and whichever was carried more is the better number. The same table holds sleep and resting HR.
- **Generic webhook:** `POST /api/webhooks/health` with `{source, samples: [{metric, date, value}]}`, `X-Webhook-Token`, idempotent upsert per (date, source, metric).

### G4. Questions raised by the findings
See §E (E5–E8).
