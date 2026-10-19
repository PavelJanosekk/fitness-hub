# Technical Specification: Self-Hosted Nutrition & Calorie Tracker Module

> **Status:** original spec provided by the user on 2026-10-17, saved verbatim (only Markdown
> headings/lists/fences restored). To be implemented **after** the core phases in `CLAUDE.md`.
> Review notes, verified API facts and proposed changes: `docs/plan-review-2026-10-17.md`.
> The **Amendments** section below is binding and overrides the original text where they conflict.

## Amendments (accepted 2026-10-17)
Ids refer to `docs/plan-review-2026-10-17.md`; the verified USDA/OFF facts behind them are in its evidence table.

**Integration with the core app**
- **SQLModel + PostgreSQL only** (no SQLite; JSONB, `pg_trgm`, `unaccent` are required) **[B2]**. Alembic migrations, UUID PKs for client-created rows, `timestamptz`, `logged_date` computed in `APP_TZ` — per `docs/SPEC.md` §3.
- **Separate nutrition assistant [E2]:** its own system prompt and toolset, running on the shared `gemini_service` runner, its own conversations (`chat_conversations.assistant = 'nutrition'`). The coach does not log foods. It keeps only the quick-kcal tool `log_quick_intake_from_ai` (inherited from the original spec) and reads intake totals via `get_body_metrics_summary`.
- **Intake single source of truth [E1]:** `meal_logs` / `meal_log_items` already exist from Phase 1 (quick-add items with manual kcal/macros). This module extends them; it does not create new meal tables.
- **Voice [B4]:** reuse `VoiceRecorder` → backend → Gemini audio (with the ffmpeg fallback). No Web Speech API.
- **Layout [B5]:** `services/nutrition/{usda.py, off.py, resolver.py, kt_import.py, nutrients.py}`, routes in `routers/nutrition.py` under `/api/nutrition`, pages `Nutrition.tsx` + `FoodDatabase.tsx`, 5th nav tab "Jídlo".

**Save flow [E4] — hybrid**
- `log_meal_from_items` saves directly only when every item resolves to a food via a **confirmed** alias or an exact match on a confirmed food. Otherwise it returns a **draft meal card** (matched food, grams, kcal, source badge, "swap food" action); the user edits/confirms with one tap.
- Aliases are created/upgraded **only on confirmation** (`food_aliases.confirmed`) **[C6]** — a wrong auto-pick must never become a permanent mapping.

**Schema changes (vs. §2 below)**
- `foods`: `kcal`, `protein_g`, `carbs_g`, `fat_g` required; `sugar_g`, `saturated_fat_g`, `fiber_g`, `salt_g` **nullable**; `micronutrients` JSONB holds **only keys with known values** — never fill unknowns with 0 **[C1]**. `source` enum adds `web_estimate` and `recipe` **[C5][C9]**. Add `micros_reference_food_id` (FK `foods.id`) + `micros_reference_ratio` (generalized hybrid enrichment, e.g. 92 % chicken ham → USDA chicken, or KT food → USDA equivalent) **[C10]**. *Superseded by E26:* a food has any number of references in `food_micro_refs(food_id, ref_food_id, grams_per_g)` (92 % chicken ham → USDA chicken 0.92; a home recipe → its ingredients); a micro the food doesn't know itself = Σ reference value × grams_per_g, over the references that know it. `foods.micros_status` (null = not tried yet, `mapped`, `unmatched`, `manual`) drives the background mapper. Add `recipe_yield_g` (cooked weight of a recipe).
- `food_aliases`: add `confirmed` (bool). Normalize with lowercase + `unaccent` + whitespace collapse; key primarily on the LLM's canonical nominative name, secondarily on the raw phrase (Czech inflection: "kuřecích stehen" ≠ "kuřecí stehno") **[C7]**.
- `meal_log_items`: **no snapshot columns** — nutrients are computed live from `foods` (fixing a food fixes its history) **[C8]**. Adds `food_id` (nullable FK) + `amount_g`; the Phase 1 manual nutrient fields remain for quick-add items.
- New `food_portions(food_id, label_cs, grams)` — "1 rohlík = 43 g", "1 kelímek = 140 g"; seeded from USDA `foodPortions` / OFF `serving_quantity`; the unit list in the system prompt moves here and LLM unit guesses become the fallback **[C9]**.
- New `recipe_components(recipe_food_id, ingredient_food_id, amount_g)` — batch cooking ("2 kg guláše, snědl 400 g"): per-100 g values = sum of ingredients / `recipe_yield_g` **[C9]**.
- New nutrition profile/targets (sex, birth year, height; kcal and macro targets, optionally different on training vs. rest days) + a static RDI reference table (EU NRV / DRI) in code **[C9]**.

**USDA client — corrected mapping [C2]** (map by `nutrientId` only; `nutrientNumber` is the old 3-digit scheme)
- Energy kcal: `1008` → fallback `2048` (Atwater specific) → `2047` (Atwater general).
- Protein `1003`; fat `1004`; carbs `1005` → fallback `1050` (by summation); fiber `1079`; **sugars `2000` → fallback `1063`** (Foundation uses 1063); **saturated fat `1258`** (missing in the original mapping).
- **Salt** has no USDA field: `salt_g = sodium_mg × 2.5 / 1000`.
- Minerals and vitamins as listed in §3A, except folate: use **DFE `1190`** (DRIs are defined in DFE), fallback `1177`. Vitamin D in µg is `1114` (`1110` is IU — ignore).
- ω-3 (approx.) = `1404` ALA (fallback `1270` 18:3 undifferentiated) + `1278` EPA + `1272` DHA + `1280` DPA. ω-6 (approx.) = `1316` LA (fallback `1269` 18:2 undifferentiated) + `1271` 20:4.
- Candidate selection: Gemini picks the best of ~10 candidates with a structured output incl. a confidence score; low confidence → draft card. (Foundation-only search ranks poorly, e.g. "potatoes boiled" → kale + potato flour; always include SR Legacy.)
- **Strategy E3 — decided 2026-10-17: bulk seed.** SR Legacy (2018-04) + Foundation (`foundation_food` rows) are imported from USDA's **CSV** downloads (pinned URL + sha256; streamed, no 210 MB JSON in memory) into `foods` (`source = usda`, `external_id = usda:<fdc_id>`) with their portions. The resolver searches them locally (`pg_trgm` on `name_en`); there is no USDA API client and no `USDA_API_KEY`. §3A's endpoint/`DEMO_KEY` text is superseded; its nutrient mapping (as corrected above) applies to the CSV `nutrient_id`s.

**Open Food Facts [C4]**
- **Barcode first:** EAN scanning in the PWA (`BarcodeDetector` on Android Chrome, `@zxing/browser` fallback; needs HTTPS) → `GET /api/v2/product/{ean}.json` (reliable).
- Text search is best-effort via the new `https://search.openfoodfacts.org/search?q=...` (the legacy `cgi/search.pl` returned 0 hits / "temporarily unavailable" in testing), with Gemini choosing among candidates.
- Always send a custom `User-Agent`; respect ~10 searches/min. Read `energy-kcal_100g` (`energy_100g` is kJ). Missing nutrient keys stay null.

**Web-grounded fallback [C5]:** Google Search grounding (kosik.cz, rohlik.cz, kaloricketabulky.cz) runs as a **separate, isolated Gemini call** (not combined with function tools in one request), and results are stored with `source = web_estimate` and a low-confidence badge in the UI.

**Smart lookup for unknown dishes [E30, 2026-10-19]** (extends C5; Google Search grounding is not in the free tier):
- Trigger: an item without a confirmed match that has no candidates, gets no pick from the chooser, or is a composite dish (`is_dish`, set by the assistant) picked with confidence < 0.6. Also on demand from the draft card ("Dohledat recept", `POST /api/nutrition/lookup`).
- Recipe source: DuckDuckGo's HTML search (`html.duckduckgo.com/html/?q=<dish> recept`, no API key), then up to 3 result pages; the first one with a schema.org `Recipe` in JSON-LD (`recipeIngredient`, `recipeYield`) is used. The page's own `nutrition` values are ignored (user decision). No web recipe → Gemini writes a typical recipe for one portion.
- One Gemini lite call (structured) turns the ingredient lines into `{name_cs, usda_query_en, grams, grams_in_dish, assumed}` plus `portions`. The finished weight `yield_g` = Σ `grams_in_dish` (per ingredient: dry pasta/rice ×2.5–3, meat ×0.7; a single overall estimate came out far too low in the live check), kept within 0.3–3× the raw mass. Each ingredient resolves through the local USDA search (hidden E28 duplicates included, as references); the dish's per-100 g kcal/P/C/F = Σ ingredient values / `yield_g`. Gemini never supplies nutrient numbers. Unresolved ingredients are listed, not guessed; under 75 % of the mass resolved the computation is rejected.
- Always a draft (E4). Confirming creates a `source = recipe` food: `recipe_yield_g`, `recipe_components` (USDA ingredients, recipe grams), micro refs = ingredients / yield (micros and optional macros flow through E26), a "porce" portion, `foods.source_url`, and the aliases. Values are recomputed on the server from the ingredient ids.
- `MealItemInput.portions`: "1 porce bun cha" without grams → amount = portions × the recipe's (or a known food's) "porce" portion.
- The numbers-only AI estimate (C5, `web_estimate`) stays as the last resort for non-dishes and failed recipe lookups.

**Prompt context [C7]:** include the user's ~150 most-used foods (id + canonical name + typical portion) in the nutrition assistant's prompt so known foods come back as a `food_id` directly and skip the resolver.

**Daily summary [C1]:** each nutrient total comes with **coverage** (share of the day's kcal from foods that have a value for it); the micronutrient grid shows it so partial data isn't read as a deficiency.

**KalorickéTabulky [C10][G2]:** the user is not on Premium, so there is no file export. Data loads through the **`kaloricketabulky-sdk`** Python package (`tomasvotava/kaloricketabulky`; MIT, async, read-only, httpx + pydantic), pinned to an exact version. This replaces §3C's scraper/file modes. Details are in review §G2.
- `client.login(email, password)` with `KALORICKETABULKY_EMAIL` / `KALORICKETABULKY_PASSWORD` from `.env`. Credentials are never stored in the DB. When the session expires, log in again.
- **Weight history:** `get_snapshot(SnapshotType.WEIGHT, from, to)` → `daily_metrics.weight_kg`. It fills only days that have no value yet.
- **Diary:** `get_diary(day)` runs once per day of the chosen range as a background job. The job is **throttled** (about 1 request per 2 s, per the SDK author's request) and **resumable** (it stores the last imported day and can continue after a stop or failure). Its progress shows in the UI.
- Mapping:
  - KT meal slot titles → `meal_type`: Snídaně → breakfast, Dopolední svačina → morning_snack, Oběd → lunch, Odpolední svačina → afternoon_snack, Večeře → dinner, Druhá večeře → second_dinner.
  - Foodstuff `guidType` → `foods.external_id` (dedupe), `title` → `name_cs`, `source = kaloricke_tabulky`.
  - Grams are parsed from `unit` (`"2 x kus (90 g)"`, `"0,6 x porce (50 g)"`, Czech decimal comma). Per-100 g values = entry value / grams × 100. **Verify on one real day first** whether the grams in parentheses are the entry total or per unit, and whether nutrient values are per entry. Entries without grams (e.g. ml) go to `warnings`, and ml are treated as g only for drinks.
  - KT nutrient fields → `foods` columns: energy, protein, carbohydrate, fat, fiber, sugar, salt, saturatedFattyAcid. `sodium` and `calcium` go into the `micronutrients` JSON in mg after unit verification. Everything else is ignored.
  - Diary `activities` are **not** imported (Strava and the health sources own activity data).
- KT foods have no vitamins or other minerals, so link them to a USDA equivalent through `micros_reference_food_id` (an optional, Gemini-assisted background step for frequently eaten foods).
- Tests are built from one real diary day, anonymized. The SDK's own fixtures contain random values.
- **E16 (2026-10-17):** imported items keep KT's exact per-day kcal/protein/carbs/fat (the user's own recipes change composition daily and the API exposes no ingredients), the only exception to C8. The KT food is refreshed to the newest composition seen. O3 verified: grams = count × unit grams, nutrients per entry, Na/Ca in g.

---

## 1. Overview & Architecture Goal
We are extending the existing web application (Python Backend, React Frontend, Dockerized, using Gemini API) with a **Self-Hosted Nutrition & Calorie Tracker** module ("Vlastní Kalorické Tabulky").

### Core Workflow (Lazy-Populated Local Database):
1. **Dictation / Chat Input:** The user inputs a meal in natural Czech (voice transcript or text), e.g., *"K obědu jsem měl 200g kuřecích stehen bez kůže na lžíci sádla a 300g vařených brambor."*
2. **LLM Extraction (Gemini API):** Gemini parses the input, corrects STT (speech-to-text) errors, converts informal units (spoons, pieces, cups) to grams, and extracts a structured list of ingredients with both a normalized Czech name and an English USDA query equivalent.
3. **Local-First Resolution:** For each ingredient, the backend first searches the **Local Database** (`foods` and `food_aliases`).
4. **External API Fallback & Auto-Caching:**
   - If the food is **NOT in the Local DB**, the backend queries the free **USDA FoodData Central API** (for raw/basic ingredients with full micronutrients) or **Open Food Facts API** (for branded Czech supermarket products).
   - The fetched nutritional profile (macros + micronutrients per 100g) is **permanently saved into the local `foods` table** (and the user's phrase is saved in `food_aliases`).
5. **Meal Logging:** The backend calculates the exact macros and micronutrients for the consumed gram weight and records the entry in `meal_logs` and `meal_log_items`.
6. **Historical Import from KalorickéTabulky.cz:** Provide an import service/endpoint that pulls existing user diary logs and food items from *KalorickéTabulky.cz* so the user doesn't start with an empty database.

---

## 2. Database Schema (SQLAlchemy / PostgreSQL or SQLite)

### Table: `foods`
Stores all known ingredients and products (normalized to **100g**).
- `id` (UUID / Integer PK)
- `name_cs` (String, indexed) – Canonical Czech name (e.g., *"Kuřecí stehno, bez kůže, syrové"*)
- `name_en` (String, nullable, indexed) – Canonical English name (e.g., *"Chicken, thigh, meat only, raw"*)
- `brand` (String, nullable) – Brand/manufacturer for packaged goods (e.g., *"Vodňanské kuře"*, *"Madeta"*)
- `ean` (String, nullable, unique, indexed) – Barcode if applicable
- `source` (Enum: `usda`, `openfoodfacts`, `kaloricke_tabulky`, `custom`)
- `external_id` (String, nullable, indexed) – e.g., USDA `fdcId` or OFF code
- `is_raw` (Boolean, default True) – Indicates if values are for raw or cooked state
- **Macronutrients (per 100g - Float, non-null, default 0.0):**
  - `kcal`
  - `protein_g`
  - `carbs_g`
  - `sugar_g`
  - `fat_g`
  - `saturated_fat_g`
  - `fiber_g`
  - `salt_g`
- **Micronutrients (per 100g - JSON / JSONB column `micronutrients`):**
  - Standardized keys with float values in standard units:
    `{"vitamin_a_ug": 0, "vitamin_c_mg": 0, "vitamin_d_ug": 0, "vitamin_e_mg": 0, "vitamin_k_ug": 0, "vitamin_b1_mg": 0, "vitamin_b2_mg": 0, "vitamin_b3_mg": 0, "vitamin_b5_mg": 0, "vitamin_b6_mg": 0, "vitamin_b9_ug": 0, "vitamin_b12_ug": 0, "calcium_mg": 0, "iron_mg": 0, "magnesium_mg": 0, "phosphorus_mg": 0, "potassium_mg": 0, "sodium_mg": 0, "zinc_mg": 0, "copper_mg": 0, "manganese_mg": 0, "selenium_ug": 0, "omega3_g": 0, "omega6_g": 0}`
- `created_at`, `updated_at` (Timestamps)

### Table: `food_aliases`
Maps user slang, STT quirks, or shorthand phrases directly to a verified `food_id` so repeated lookups bypass external APIs and LLM ambiguity.
- `id` (PK)
- `alias_normalized` (String, unique, indexed) – Lowercase, stripped Czech phrase (e.g., *"krůtí maso z albertu"*, *"babišovo maso"*, *"batáty syrové"*)
- `food_id` (FK -> `foods.id`, on delete cascade)
- `default_portion_g` (Float, nullable) – Optional default weight (e.g., `140.0` for *"kelímek skyru"*)

### Table: `meal_logs`
Represents a single meal event.
- `id` (PK)
- `logged_date` (Date, indexed)
- `meal_type` (Enum: `breakfast`, `morning_snack`, `lunch`, `afternoon_snack`, `dinner`, `other`)
- `raw_user_input` (Text, nullable) – Original dictated prompt
- `notes` (Text, nullable)
- `created_at` (Timestamp)

### Table: `meal_log_items`
Individual ingredients within a `meal_log`.
- `id` (PK)
- `meal_log_id` (FK -> `meal_logs.id`, on delete cascade)
- `food_id` (FK -> `foods.id`)
- `amount_g` (Float) – Consumed weight in grams
- `snapshot_kcal` (Float) – Cached calculation (`food.kcal * amount_g / 100`)
- `snapshot_protein_g` (Float)
- `snapshot_carbs_g` (Float)
- `snapshot_fat_g` (Float)

---

## 3. External Data Sources & API Clients

### A. USDA FoodData Central Client (`USDAFoodClient`)
- **Endpoint:** `GET https://api.nal.usda.gov/fdc/v1/foods/search`
- **Env Variable:** `USDA_API_KEY` (defaults to `DEMO_KEY` for dev, configurable in `.env`).
- **Filtering:** Always query with `dataType=["Foundation", "SR Legacy"]` and `pageSize=5`. Do NOT use `"Branded"` unless explicitly requested, to ensure high-quality laboratory micronutrient profiles.
- **Nutrient ID Mapping:** Map USDA `foodNutrients` array (by USDA `nutrientNumber` or `nutrientId`) into our `foods` macro columns and `micronutrients` JSON structure:
  - Energy (kcal): `1008` (or Atwater General `2047` / Specific `2048` fallback)
  - Protein: `1003`, Total lipid (fat): `1004`, Carbohydrate: `1005`, Fiber: `1079`, Sugars: `2000`
  - Minerals: Calcium `1087`, Iron `1089`, Magnesium `1090`, Phosphorus `1091`, Potassium `1092`, Sodium `1093`, Zinc `1095`, Copper `1098`, Manganese `1101`, Selenium `1103`
  - Vitamins: Vit C `1162`, Thiamin (B1) `1165`, Riboflavin (B2) `1166`, Niacin (B3) `1167`, Pantothenic acid (B5) `1170`, Vit B6 `1175`, Folate (B9) `1177`, Vit B12 `1178`, Vit A (RAE) `1106`, Vit E `1109`, Vit D `1114`, Vit K `1185`.

### B. Open Food Facts Client (`OpenFoodFactsClient`)
- Used when `is_packaged_product == True` or when searching by EAN barcode.
- **Endpoints:**
  - Barcode lookup: `GET https://world.openfoodfacts.org/api/v2/product/{ean}.json`
  - Text search (Czech preference): `GET https://cz.openfoodfacts.org/cgi/search.pl?search_terms={query}&search_simple=1&action=process&json=1&page_size=5`
- **Hybrid Micronutrient Enrichment (Optional Enhancement):** If a packaged product (e.g., 92% chicken ham) only returns macros from OFF, allow linking a base USDA raw ingredient (`base_usda_query_en`) with a ratio (`0.92`) to estimate its micronutrient JSON.

### C. KalorickéTabulky.cz Importer (`KalorickeTabulkyImporter`)
- Implement a service to import existing user data from *KalorickéTabulky.cz*.
- Support two modes:
  1. **Direct Scraper/Client:** Using user credentials/session cookie (similar to community `kaloricketabulky-sdk` patterns) to fetch daily logs and custom foods from the KT web/mobile endpoints.
  2. **File Import:** Parsing exported CSV/XML/JSON data if provided manually.
- Deduplicate imported foods by `external_id` (KT `pId` / food ID) and store with `source="kaloricke_tabulky"`.
- Background task option: Enrich frequently eaten imported KT raw ingredients with USDA micronutrients via Gemini translation.

---

## 4. Gemini API Chatbot & Resolution Pipeline

Use the official `google-genai` Python SDK.

### System Prompt Guidelines for the Nutrition Agent:
1. You are a Czech nutrition assistant. The user dictates what they cooked or ate (often via voice transcription with minor typos, e.g., *"britský maso"* instead of *"krůtí maso"*).
2. Convert informal Czech measures to grams (`1 lžíce oleje/sádla` = 12–15g, `1 lžička` = 5g, `1 kelímek jogurtu/skyru` = 140–150g, `1 vejce M` = 55g, `1 rohlík` = 43g, `1 krajíc chleba` = 60g).
3. Distinguish between:
   - **Basic/raw culinary ingredients** (`is_branded = False`): Strip irrelevant store/brand names (e.g., *"kuřecí maso z Alberta od Babiše"* -> `name_cs="Kuřecí maso, syrové"`, `usda_query_en="Chicken, meat only, raw"`). Specify `raw` vs `cooked/boiled/roasted` in `usda_query_en` based on how the user weighed it.
   - **Packaged/processed Czech products** (`is_branded = True`): Keep brand names or map colloquialisms (e.g., *"šunka od Babiše"* -> search query `"Kostelecké uzeniny šunka"` or `"Vodňanské kuře šunka"`).

### Tool Calling / Resolver Flow (`resolve_and_log_meal`):
When the user logs a meal, Gemini invokes the tool `log_meal_from_items(meal_type, logged_date, items)` where each item in `items` has:
```json
{
  "user_phrase": "krůtí prsa z alberta",
  "canonical_name_cs": "Krůtí prsa, syrová",
  "usda_query_en": "Turkey, breast, meat only, raw",
  "is_branded": false,
  "brand_search_query": null,
  "amount_g": 250.0
}
```

#### Backend Resolution Algorithm (for each item):
1. **Check `food_aliases`:** Look up `alias_normalized = normalize(item.user_phrase)` or `normalize(item.canonical_name_cs)`. If found, return `food_id`.
2. **Check `foods` table:** Fuzzy/ILIKE match on `foods.name_cs` or `foods.name_en`. If high-confidence match exists, save new alias in `food_aliases` and return `food_id`.
3. **External Lookup (Cache Miss):**
   - If `is_branded == False`:
     - Call `USDAFoodClient.search(item.usda_query_en)`.
     - If multiple candidates return, select the best match (either via heuristic scoring on shorter canonical description or a fast Gemini structured selection call).
     - Insert the new record into `foods` (with full macros + micronutrients JSON) and create the alias in `food_aliases`.
   - If `is_branded == True`:
     - Call `OpenFoodFactsClient.search(item.brand_search_query)`.
     - If found, insert into `foods` (and optionally enrich micronutrients from `item.usda_query_en`).
     - If not found in OFF, fallback to Gemini with Google Search Grounding (searching kosik.cz, rohlik.cz, kaloricketabulky.cz) or USDA equivalent, and cache the result in `foods`.
4. **Create Log Entry:** Insert `meal_logs` and `meal_log_items` and return a structured summary to Gemini (including total kcal, macros, top micronutrients, and whether each item was loaded from local DB or newly cached from USDA/OFF).

---

## 5. REST API & Frontend Requirements

### Backend Endpoints (FastAPI):
- `POST /api/nutrition/chat` – Send natural language message to the nutrition chatbot; returns assistant reply + logged meal card data + source badges (Local DB, Cached from USDA, Cached from OFF).
- `GET /api/nutrition/summary?date=YYYY-MM-DD` – Returns daily totals for calories, macros, and all tracked micronutrients (with % of Daily Recommended Intake / RDI), plus list of meals.
- `GET /api/nutrition/foods?q=...` – Search local foods database, edit nutrients, or manually add custom foods.
- `POST /api/nutrition/import/kaloricke-tabulky` – Trigger import of historical logs and foods from KalorickéTabulky.cz.

### React Frontend Components:
- **Chat / Quick-Log Widget:** Text input + microphone dictation button (Web Speech API cs-CZ or backend audio transcription) showing real-time resolution badges (e.g., "Krůtí prsa (250g) – Nově staženo z USDA a uloženo do lokální DB").
- **Daily Dashboard:**
  - Macro rings/bars (Calories, Protein, Carbs, Fat, Fiber).
  - Micronutrient Grid: Progress bars for key vitamins (B-complex, C, D, A, E, K) and minerals (Iron, Magnesium, Zinc, Potassium, Calcium, Sodium, Selenium).
  - Meal timeline (Breakfast, Lunch, Dinner, Snacks) with inline gram editing and delete actions.
- **Local Food Database Manager & Importer:** Table view of all cached foods in the local DB (source filter, search, manual edit) and a button/modal to run the KalorickéTabulky.cz import.

---

## 6. Implementation Plan for the Coding Agent
Please implement this step-by-step:
1. **Step 1:** Create SQLAlchemy models (`foods`, `food_aliases`, `meal_logs`, `meal_log_items`) and database migrations.
2. **Step 2:** Implement `USDAFoodClient` (with exact USDA nutrient ID mapping for macros and 22+ micronutrients) and `OpenFoodFactsClient`.
3. **Step 3:** Implement the `FoodResolverService` (Local DB lookup -> External API fallback -> Local DB caching) and unit tests.
4. **Step 4:** Implement the Gemini API service with tool calling (`log_meal_from_items`, `get_daily_nutrition_summary`) and FastAPI routes.
5. **Step 5:** Implement the `KalorickeTabulkyImporter` service.
6. **Step 6:** Build the React frontend pages/components (Chat Logger, Daily Macro/Micro Dashboard, Local Food DB table).
