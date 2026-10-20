# Bucket list module (+ Hrdina tab)

Status: **accepted 2026-10-20 (E36)**: B1–B5, B7, B8 as recommended; **B6: no retroactive XP**; every idea 1–11
wanted (auto-complete must announce itself with a modal, not happen silently). Backlog D5; side quests D6 later
(the user: quick ones for a spare moment, longer ones for a weekend / month). Numbers marked *(tune)* are starting
values.

## Goal (user, 2026-10-20)
- A bucket list in the app: add / remove / edit items, categories (travel, fitness, …), a difficulty.
- Completing an item gives the hero bonus XP.
- Navigation: the **Rutina** tab becomes a **Hrdina** tab with sub-tabs: Rutina, Bucket list, later **Side questy**
  (every day at least one side quest from a list).
- No bulk import: the user's list (CSV pasted in chat, 9 groups, ~260 rows) is seeded once, like the habits seed.
- Trips: other countries → bucket list, trips nearby → side quests (user's lean; see B5).

## Decisions (agent recommendation first)
- **B1 Navigation.** Bottom nav *Rutina* → **Hrdina** (`/hero`), sub-tabs **Rutina** (default; Den / Měsíc as
  today) · **Bucket list** · **Postava** (today's `/hero` page: XP history, skills, boss, badges, pauses).
  *Side questy* is added between Bucket list and Postava when D6 is built. Old URLs (`/habits`, `/habits?v=month`)
  redirect. Přehled stays as it is.
- **B2 Fields.** title, category, difficulty, status (open / planned / done), `done_on` date, `planned_for` date
  (optional; a planned item shows a countdown like races), note, link, travel time (free text, e.g. "3 h 15 min"),
  `done_before_app` flag, sort order, created_at. Completing asks for the date (default today) and an optional
  memory note.
- **B3 Categories:** a fixed set of 8 with icon + colour (like the habit areas), not user-editable:
  Cestování (countries) · Výpravy (mountains / lakes / multi-day trips by car) · Zážitky · Adrenalin ·
  Sport & pohyb · Dovednosti · Jídlo & pití · Tělo & mysl.
- **B4 Difficulty = loot rarity** *(tune)*: Běžná 50 XP (grey) · Vzácná 150 XP (blue) · Epická 400 XP (violet) ·
  Legendární 1 000 XP (orange). For scale: level 12 → 13 needs ~4 200 XP, a weekly quest pays 150.
  XP lands on `done_on` in the live ledger (multiplier and tired debuff apply like any gain); un-ticking removes it.
  No penalties (a bucket list is lifelong).
- **B5 Skill + split.** A new 7th skill **Dobrodružství** fed by the bucket list (and later side quests); it does not
  rust until side quests exist. Bucket list = countries, places, activities, skills, food, plus the far trips
  (*Cestovat okolí*, *Zahraničí*: 2.5–6 h drive, a weekend). The 110 *Výlety – Tipy* (≤ 2.5 h day trips) go to the
  side-quest pool; they are kept as seed data and imported when D6 is built.
- **B6 Items done before the app** (34 rows marked *Hotovo*): imported as done with `done_before_app`, **0 XP**,
  but they count for progress, % and badges. (Alternative: XP on the seed day, ~+3 900 XP ≈ one level at once.)
- **B7 Clean-up of the list:** Czech titles, typos fixed, duplicates merged (table below). The original text is
  kept in the seed file only.
- **B8 v1 extras** (from the ideas below): rarity look, progress header by category, filters, "Naplánováno" with a
  date, memory note, badges, coach tools, auto-complete of *Uběhnout maraton* by the boss. The rest later.

## Ideas (for the user to pick)
1. **Auto-complete from app data:** *Uběhnout maraton* when the marathon boss is defeated (2. 5. 2027, legendary
   + confetti); *Muscle up / L-sit / stojka / planche* when a set of that exercise is logged; *Vylézt na horu* from
   a Strava hike with ≥ 1 000 m elevation.
2. **Naplánováno:** pick a date → countdown tile on Hrdina, like races; a planned item can become that week's quest.
3. **Memory on completion:** date, a sentence, ★ 1–5, later a photo → a "Síň slávy" timeline of what was done.
4. **Scratch map of the world:** countries done / planned coloured on a map (Leaflet is already in the app; needs
   a ~250 kB country GeoJSON); a continent counter feeds *Navštívit všech 7 kontinentů* (now 2/7).
5. **Map of trips** with pins (coordinates written once by the agent, no geocoding API); later shared with side
   quests: "what's within 1 hour".
6. **Letošní cíle:** star 3–5 items for the year; a yearly quest "splň 5 položek letos" with a bonus.
7. **Kostka osudu:** a random open item by filter (e.g. Běžná + Jídlo) for a free weekend.
8. **Badges:** first item, 10 / 25 / 50 done, a whole category, Gurmán (all food), Adrenalin junkie, 7 continents.
9. **Coach:** "splnil jsem bungee" by voice ticks it (`complete_bucket_item`), and the coach can suggest an item that
   fits the plan (a long run in Moravský kras, no skydiving in race week).
10. **Season / cost tags** (léto, zima, €–€€€) for filtering what fits now.
11. **Progress items** with steps (Naučit se rusky: A1 → A2 …), small XP per step.

## Seed mapping (B5–B7)
Format: Czech title · rarity (1 Běžná … 4 Legendární) · ✓ = done before the app · drive time. Original text in
brackets where it changed beyond translation.

**Jídlo & pití** — ✓ Dračí ovoce 1 · ✓ Pořádný steak 1 · ✓ Hmyz 1 · ✓ Ústřice 1 · ✓ Sushi 1 · ✓ Kimči 1 ·
✓ Sépie 1 · ✓ Wasabi 1 · ✓ Klokaní maso 1 · ✓ Voda přímo z pramene 1 · ✓ Domácí sushi 2 · ✓ Topinambur 1 ·
Humr 2 · Lanýže 2 · Obsluha u stolu (table side service) 2 · Laverbread 2 · Hovězí jazyk 1 · Mořský ježek 2 ·
Nové koření 1 · Nové koktejly 1 · Nejpálivější chilli 2 · Chilli lízátko 1 · Belgická čokoláda 1 · Bubble tea 1 ·
Bloody Mary 1 · Guinness 1 · Krocan jako na Díkůvzdání 2 · Vlastní těstoviny 1 · Uvařit vlastní pivo 3

**Cestování** (Země + Zahraničí – Nápady, merged) — ✓ Itálie 2 · ✓ Chorvatsko 2 · ✓ Rusko 2 · ✓ Asie 3 ·
✓ Japonsko 3 (the idea list's *Japonsko* merged in) · ✓ Španělsko 2 · USA – národní parky 4 (*America* + *US Narodni
parky*) · Havaj 4 · Nový Zéland 4 · Francie 2 · Vietnam 3 · Thajsko 3 · Švýcarsko 2 · Kyrgyzstán + Uzbekistán 3 ·
Island 3 · Čína 3 · Indonésie (Bali) 3 · Albánie 2 · Jižní Korea 3 · Azory 3 · Kanada 3 · Skotsko (Edinburgh
i příroda) 2 · Filipíny 3 · Skandinávie (Švédsko / Norsko / Finsko) 3 · Málaga (levně) 2 · Peru 4 · Jordánsko 3 ·
Sicílie 2

**Výpravy** (Cestovat okolí + Zahraničí + mountains from Místa, merged) — ✓ Praděd 1 · ✓ Dolní Morava 1 ·
Jizerské hory 2 (3 h 2 min) · České Švýcarsko – Pravčická brána 2 (3 h 55 min) · Sněžka 2 (2 h 30 min) ·
Ještěd 1 (3 h 15 min) · Prachovské skály 1 (2 h 30 min) · Šumava – Bílá strž (vodopády) 2 (4 h 22 min) ·
Beskid Żywiecki 2 · Achensee 2 (6 h 18 min) · Orlí hnízdo 2 (5 h 4 min) · Wolfgangsee 2 (4 h 40 min) ·
Hochschwab 3 (4 h) · Pieniny 2 (5 h) · Tatry 3 · Kaprun 2 (6 h) · Attersee 2 · Přechod Dolomit 4

**Zážitky** — ✓ Dovolená v zahraničí 1 · ✓ Akvárium 1 · ✓ Plavat s medúzami 2 · ✓ Spát v týpí 1 ·
✓ Plavat pod vodopádem 2 · ✓ Výlet s přáteli (friendcation) 2 · ✓ Divadlo 1 · ✓ Koupání nahý 1 · ✓ Geocaching 1 ·
Plavba lodí (cruise) 3 · Safari 4 · Deštný prales 3 · Havajská luau 2 · Spát na hausbótu 2 ·
Navštívit všech 7 kontinentů 4 · Motýlí farma 1 · Mayské ruiny 4 · Pyramidy 4 · Let balónem 3 · Muzikál 1 ·
Koncert oblíbené kapely 2 · Jízda limuzínou 1 · Laser game 1

**Adrenalin** — ✓ Čtyřkolka 1 · ✓ Paintball 1 · Seskok padákem 3 · Bungee jumping 3 · Potápění s přístrojem 3 ·
Rogalo 3 · Zipline 1 · Mechanický býk 1 · Řídit motorku 2 · Řídit sporťák 2

**Sport & pohyb** — ✓ Kajak 1 · ✓ Six pack 3 · Uběhnout maraton 4 · Snowboard 2 · Squash 1 · Surfování 2 ·
Jízda na koni 1 · Vylézt na horu 2 · Lezecká stěna 1

**Dovednosti** — ✓ Muscle up 3 · Kalistenika 3 · L-sit 2 · Stojka 3 · Planche 4 · Naučit se šachy 2 ·
Naučit se rusky 4

**Tělo & mysl** — Solárko 1 · Masáž 1 · Reiki 1 · Akupunktura 1 · Týden vegetariánem 2 · Týden veganem 2 ·
Dobrovolnictví 2 · Překonat celoživotní strach 3

**Side-quest pool (D6, not in the bucket list):** the 110 *Výlety – Tipy* rows (name, drive time / km, link) as sent.

The user's original list is saved verbatim in `data/imports/bucket_list_2026-10-20.csv` (gitignored, main checkout).

## Implementation (E36)
Phase 8 in `docs/PROGRESS.md`. Rules as built (`services/bucket.py`, `/api/bucket`, migration 0022):
- **Tables:** `bucket_items` (fields of B2 plus `season`, `cost` 1–3, `year_goal` (year), `rating` 1–5, `memory`,
  `auto_rule` / `auto_exercise_id` / `auto_threshold`, `country_codes` (ISO alpha-2, JSONB), `lat` / `lon`),
  `bucket_steps` (milestones), `visited_countries` (map; CZ seeded as home). The migration seeds the 132 items above
  and adds the exercises Muscle Up, L-Sit, Handstand, Planche (also in `app.seed`).
- **State is live:** done = `done_before_app`, else `done_on` (by hand), else the auto rule's first day:
  marathon = a run >= 42 km, or >= 40 km on a race day; exercise = a completed set of it; hike = Hike / Walk with
  elevation gain >= threshold (1 000 m); continents = visited continents >= threshold (7). Countries = map rows plus
  the codes of completed items; continents from `app/data/continents.py` (Natural Earth 1:50m, public domain).
- **XP** (skill Dobrodružství, kinds `bucket*`): rarity 50 / 150 / 400 / 1 000 on the completion day; +50 % for a
  starred year goal done in its year; 25 per finished step; 5 paying items in a calendar year +500 once. Nothing for
  `done_before_app` or completions more than 7 days before the item was added (B6). Bucket XP also counts on paused
  days; Dobrodružství never rusts. Un-ticking removes the XP (the ledger is live).
- **Badges:** first item, 10 / 25 / 50 / 100 items, legendary item, Gurmán (20 food), Adrenalinový junkie (5),
  Cestovatel (10 countries), all 7 continents, Rok dobrodružství (5 in a year). Items done before the app count from
  the day they were added.
- **World map data:** `frontend/public/world-110m.json` (Natural Earth 1:110m, coordinates rounded to 0.01°,
  properties `c` = ISO code, `k` = continent; 172 kB, 55 kB gzipped). Small countries missing at that scale are added
  from a list (all 237 codes come with the board).
