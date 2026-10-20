# Habit journal + Dovednosti (habit log modes)

Status: **accepted 2026-10-20 (E37)**: J1, J4–J8 as recommended; **J2: `review` offers an optional dovednost too**;
**J3: the tick is saved only when the sheet is confirmed**; ideas 1, 2, 3, 5 accepted, 4 (photo) later. Extends the habits module (`docs/habits-module-spec.md`,
E20) and the Hrdina tab (E36). Numbers marked *(tune)* are starting values.

## Goal (user, 2026-10-20)
Routine habits get three kinds:
1. **Jen odškrtnout:** a plain tick, as today.
2. **Poznámka + dovednost:** ticking opens a sheet for a note and a skill name. The skill is picked from the
   existing list or typed in as a new one. Both are optional. Example: *Vyzkoušet jednu novou věc* → "lezení na
   stěně, Lezec Brno" + skill *Lezení*. The skills build up a list on the hero.
3. **Hodnocení + poznámka:** like completing a bucket-list item. Stars 1–5 and a note.

## Naming
The app already uses "skill" in two places: the RPG stats (Síla, Výdrž, …, `rpg.SKILLS`) and the habit area
(`habits.skill`: Tělo / Výživa / Domov / Disciplína / Mysl). The user's new skills are a third thing: abilities
the hero has picked up. In the UI they are **Dovednosti**. In code they are `abilities`, so they don't clash
with `skill`. Postava keeps the radar of RPG skills, and Dovednosti become a card of their own.

## Decisions (agent recommendation first)
- **J1 Log mode per habit.** New column `habits.log_mode`: `check` (default) · `note` · `review`. It is set in the
  habit's add / edit sheet ("Při odškrtnutí: jen odškrtnout / poznámka a dovednost / hodnocení a poznámka").
  Existing habits stay `check`. *Vyzkoušet jednu novou věc* and *Učit se novou dovednost* switch to `note` in the
  migration.
- **J2 What each mode asks for (decided: alternative).** `note`: a note plus one optional dovednost. `review`:
  stars, a note and an optional dovednost. Every field is optional in both modes.
- **J3 Ask first, tick on confirm (decided: alternative).** Tapping an unticked note / review row only opens
  the sheet; the tick is written (optimistic, offline-queued) when **Uložit** is pressed, with or without content.
  Closing the sheet leaves the day unticked. Tapping a ticked row opens the sheet to edit its entry, with
  **Zrušit splnění** inside (J4 confirm when it has content). Ticks without content (coach, empty save) show a
  small "+ poznámka" chip.
- **J4 Unticking an entry with content.** Unticking a day that has a note, stars or a dovednost asks first
  ("Smazat i poznámku?"), because the PUT deletes the row. A bare tick unticks without asking, as today.
- **J5 Dovednosti list.** A dovednost has a name (unique ignoring case and diacritics, so "lezeni" finds
  *Lezení*) and an optional emoji/icon. It has no category in v1. First / last date and count are derived from
  the logs. You can rename it, merge two (moves the logs), and delete it (only when unused, or the logs keep
  their notes and lose the link).
- **J6 XP** *(tune)*. A tick pays as today (points × 10, a weekly habit at its target). On top of that, the
  **first entry of a new dovednost: +25 XP to Mysl** ("Nová dovednost: Lezení"). Notes and stars pay nothing,
  so writing stays honest. *Alternative:* no extra XP at all.
- **J7 Where it shows.**
  - **Rutina Den:** a note-mode row shows a pencil icon and the first line of the day's note under its title.
    A review row shows its stars.
  - **Postava:** a new card **Dovednosti** (count, the last 5 as chips, "Vše"). It opens `/hero/abilities`: a
    list sorted by last use, each with ×count, first / last date and a level by count *(tune: 1× Nováček,
    3× Začátečník, 10× Pokročilý, 25× Zkušený)*. Tapping one opens its timeline of notes.
  - **Rutina Měsíc:** a **Deník** section, a timeline of every note and rating in the month, filterable by
    habit.
- **J8 Coach.** `set_habits_done` gains optional `note`, `rating`, `ability`. The coach fills them from speech
  ("tento týden jsem zkusil lezení, bylo to super, 5 hvězd"), and the dovednost matches like exercises
  (unaccent + trigram; an unclear match returns candidates and saves no new one). There is a new read tool
  `get_abilities()` (list + counts + last notes) for questions like "co nového jsem letos zkusil?". The prompt
  rule: in note mode, ask briefly what it was if the user didn't say.

## Data model (migration 0023)
- `habits.log_mode` text not null default `check`, `one_of` constraint.
- `abilities`: `id` int PK, `name` text, `key` text unique (the name casefolded, without diacritics and extra
  spaces, computed in Python by `services/abilities.ability_key`, so the constraint is modelled and `alembic check`
  stays clean), `icon` text null, `created_at` timestamptz.
- `habit_logs` gains `note` text null (≤ 2 000 chars), `rating` smallint null (CHECK 1–5), `ability_id` FK
  `abilities.id` null (ON DELETE SET NULL). The PK `(habit_id, date)` stays, so a weekly habit keeps one entry
  per day it was done. (This replaces R2's "no `notes`, no UI for it", because there is a UI now.)
- Data step: `log_mode = 'note'` for the two habits from J1. Nothing else changes, and old ticks stay bare.

## API
- `PUT /api/habits/{id}/days/{date}` body `{done, note?, rating?, ability?}`. `ability` is a **name**, not an
  id. The server finds the dovednost by the normalized name or creates it. That keeps the write idempotent and
  lets a dovednost typed in offline replay safely. Absent fields keep what is stored, and `null` clears it. A
  bare `{done: true}` from a one-tap or the coach therefore never wipes a note. `done: false` deletes the row
  with its content.
- `GET /api/habits/board`: habits gain `log_mode`, plus `entries: {date: {note, rating, ability_id, ability}}` only
  for days with content, and the board gains `abilities: [{id, name, icon}]` (most recently used first) for the
  entry sheet offline (the `done` list stays as it is, cheap). **Query key `habits/board/v2`** (persisted cache shape
  changes).
- `GET /api/habits/abilities` (list with count, first / last date, level), `GET /api/habits/abilities/{id}`
  (timeline), `PATCH` (rename / icon), `POST /api/habits/abilities/{id}/merge` `{into_id}`, `DELETE`.
- Ledger: an `ability_new` entry (+25, skill `mind`) on the date of a dovednost's first log, computed live, so
  an untick or a merge moves or removes it. It also counts on paused days, like bucket-list XP.
- Rename to a name another dovednost has → 409 (merge instead); delete keeps the entries' notes and stars.

## UI
- **Entry sheet** (bottom sheet, like the bucket memory sheet). Title = the habit, date chip.
  - `note`: a textarea ("Co jsi dělal / vyzkoušel?") and a dovednost combobox. It searches the list as you type,
    with recent ones as chips above it, and offers "+ Přidat novou: *Lezení*" when nothing matches.
  - `review`: the existing `Stars` component, a textarea and the same dovednost combobox.
  - **Uložit** (ticks), closing = nothing saved; on a ticked day also **Zrušit splnění**. A saved entry with a new dovednost shows a small "Nová dovednost!" toast
    with the XP.
- **Habit sheet:** the "Při odškrtnutí" segmented control (J1).
- Offline: the sheet writes through the same queued day mutation (`HabitDayWrite` grows `note`, `rating`,
  `ability`), and `applyDay` puts the entry into the cached board. The abilities list for the combobox comes
  from the board cache plus the abilities query, so a name typed offline shows up at once.

## Ideas (1, 2, 3, 5 accepted; 4 later)
1. Entries with ★ 4–5 from review habits also appear in the bucket list's **Síň slávy**.
2. A bucket-list item from the *Dovednosti* category completes itself the first time a dovednost of the same
   name is logged (an auto rule like `exercise`).
3. A weekly quest "zkus novou dovednost" when Mysl is the weakest skill.
4. Photo with an entry (needs file storage, later).
5. Prompt chips in the sheet from past notes ("znovu: Lezení").

## Steps (after the decisions)
1. Backend: migration 0023, models, `set_day` with content, abilities service + routes, ledger entry, coach
   tool changes, tests.
2. Frontend: board v2 + mutation, entry sheet, habit sheet control, Den row look, Dovednosti card + page, Deník
   in Měsíc.
3. Verify on dev (tests, typecheck, headless screenshots in all themes), deploy (backup first).
