# Side quests module (D6)

Status: **accepted 2026-10-21 (E45)**: all as recommended except S7 (dropped: no daily tip, the weekly side quest is
the only rhythm). Categories are provisional until the user's list arrives. Numbers marked *(tune)* are starting values.

## Goal (user, 2026-10-20 / 2026-10-21)
- A personal list of side quests: projects and small adventures ("learn X", "do Y", "build Z", nearby day trips),
  split into quick ones (a spare moment / one day) and longer ones (a weekend / a month).
- Add / remove / edit in the app, like the bucket list. **No import mechanism**: the user's list
  (`Typ,Kategorie,Úkol,Stav`, e.g. `1 den,Learn,Watch a documentary on a topic you know nothing about,Nehotovo`)
  is seeded once by a migration, like the bucket list and habits seeds.
- Tie-in with Rutina and the RPG layer (Hrdina): "every day at least one side quest from a list" (2026-10-20),
  "one side quest has to be completed every week" (backlog D6). Exact rules decided here.
- The 100 *Výlety – Tipy* day trips (≤ 2.5 h drive) from `data/imports/bucket_list_2026-10-20.csv` are the first
  pool (B5 of the bucket-list spec).

## Decisions (agent recommendation first)
- **S1 Navigation.** A 4th sub-tab on Hrdina between Bucket list and Postava: `/hero/quests`, labels shortened to
  fit a phone: **Rutina · Bucket · Questy · Postava**.
- **S2 Fields.** title, `duration` (from *Typ*), category (from *Kategorie*), status (open / active / done),
  `done_on`, `done_before_app` (rows marked *Hotovo* in the seed: 0 XP, like B6), note, link, travel time (trips),
  memory + ★ on completion, sort order, created_at. *Active* = "rozjeto" for the longer ones, shown on top.
- **S3 Duration (Typ)** — a fixed set, the seed's values mapped onto it: **Chvilka** (≤ 1 h) · **1 den** ·
  **Víkend** · **Týden** · **Měsíc+**.
- **S4 Categories (Kategorie)** — provisional, from the user's quick split (Learn, Make, Cook/eat, Activity) plus
  the day trips: **Učení** (→ Mysl) · **Tvoření** (→ Mysl) · **Jídlo** (→ Výživa) · **Aktivita** (→ Dobrodružství)
  · **Výlet** (→ Dobrodružství). To be split smarter when the list arrives (user, 2026-10-21).
- **S5 XP by duration** *(tune)*: Chvilka 20 · 1 den 50 · Víkend 120 · Týden 250 · Měsíc+ 500, to the category's
  skill, on `done_on` in the live ledger (multiplier / tired apply); un-ticking removes it. (Bucket: 50–1 000.)
- **S6 Weekly side quest** — a new weekly quest in `quests.py`: **"Side quest týdne: dokonči 1 side quest"**,
  any duration (user, 2026-10-21), 80 XP to Dobrodružství, counts toward the all-quests bonus; unfinished =
  "Výprava nesplněna" (no extra penalty, as all quests). From Monday 2026-10-26 so old weeks keep their quests.
- **S7 Daily tip** — **dropped** (user: no side quest every day, one per week is the rhythm).
- **S8 Dobrodružství rust** — stays off (simpler; side quests mostly go to other skills anyway).
- **S9 Questy page** — weekly quest card, active quests, filters (duration chips, category, open / done, search), rows
  grouped by duration with a check, item sheet (detail, complete with date / memory / ★, edit, delete), add form.
  The trips show travel time + link; a "Kostka" (random by filter) like the bucket list.
- **S10 Coach** — tools `complete_side_quest` (fuzzy title, like bucket) and `suggest_side_quest`
  (open quests by duration/category) so "splnil jsem ten dokument" by voice ticks it.
- **S11 Badges** *(tune)*: first side quest, 10 / 50 / 100 done, 10 weeks in a row with a side quest, all trips of
  a 1 h radius.

## Seed
Sent by the user at the end of implementation (CSV `Typ,Kategorie,Úkol,Stav`); cleaned up like B7 (Czech titles,
typos, duplicates merged) and seeded with the 100 day trips in one migration.
