# Habits / routine module ("Rutina")

Status: **implemented and live** (2026-10-18, decision E20 in `docs/PROGRESS.md`): H1 a, H2 yes, H3 both, H4 the user's list. Visual mockup (private claude.ai canvas): https://claude.ai/artifact/TA62pfjToHJyZKVbUtaQQN
(1 Den, 2 Měsíc, 3 Přidat/upravit, 4 Přehled card, 5 RPG concept).

## Goal (user, 2026-10-18)
Move the user's Google-Sheets habit tracker into the app: daily routine (make bed, creatine + vitamins, Japanese
Anki, exercise, clean face, learn a new skill; bonus "don't cheat on diet" worth 2 points) and weekly tasks (try one
new thing; clean living room, bathroom, kitchen, bedroom, workroom). Add/edit/remove habits from the phone, tick
them per day, switch days, see a month overview, nice charts. **Long-term goal: an RPG layer** (weekly streaks like
"10 weeks in a row", XP bar, skills). Not now, but the design must not block it.

The sheet's model: daily rows with points (column B), a separate Bonus section (adds points, not part of the max),
per-day Points / Max / Percentage, weekly rows ticked once per week.

## Review of the user's Gemini draft (§10 addendum)
| # | Draft says | Problem | Proposal |
|---|---|---|---|
| R1 | `POST /habits/{id}/toggle` | Not idempotent. The PWA replays queued mutations after an outage (gym pattern); a replayed or double-sent toggle flips the state back. Breaks the hard rule "create/update endpoints are idempotent upserts". | `PUT /api/habits/{id}/days/{date}` with `{done: bool}`, persisted offline mutation like gym sets. |
| R2 | `habit_logs.id` + `completed_date` | Nothing stops duplicate rows for one day. | Natural PK `(habit_id, date)`. No `notes` (no UI for it). |
| R3 | Streak = "consecutive days" | Undefined edge cases: an unticked *today* must not show the streak as broken; days before the habit existed must not count. | Streak ends today if done, else yesterday; counting stops at `start_date`. Weekly: consecutive ISO weeks with done-days ≥ target, current week counts once met. |
| R4 | Completion rate over N days | A habit added mid-month would look like it failed the earlier days. Archiving would lose history (hard delete) or keep counting it. | `start_date` (editable) and `archived_at`; rates only over days the habit was active. Delete = archive; hard delete only with explicit confirmation. |
| R5 | No edit endpoint, no order | The user wants to edit and the sheet has a fixed order. | `PATCH /api/habits/{id}`, `sort_order` + `POST /api/habits/reorder` (drag handle, existing `useDragReorder`). |
| R6 | `category: morning/chores/growth/health` free text | Not useful for grouping or the RPG. | Fixed `skill` enum: body (Tělo), nutrition (Výživa), home (Domov), discipline (Disciplína), mind (Mysl). Colour + later the RPG skill that earns the XP. |
| R7 | No points | The sheet scores with points and a bonus section. | `points` (1–3) and `is_bonus`. Day % = done non-bonus daily habits / active non-bonus daily habits; points incl. bonus shown next to it (sheet parity). Later the XP base. |
| R8 | Weekly = exactly once | Common need: "gym 3× a week". | `weekly_target` (default 1); a weekly habit stores one log per day it was done (also gives "done Thu"). |
| R9 | Seed English defaults on every startup | Wrong content; re-seeding on startup would resurrect deleted habits. | Seed the user's own list (Czech, from the sheet) once, in the data migration. |
| R10 | `toggle_habit_from_ai(habit_title, completed)` | One habit per call; "splnil jsem ranní rutinu a uklidil pokoj" names several; a fuzzy match can tick the wrong one. | `set_habits_done(habit_titles: list[str], done=True, date=None)`; unaccent + trigram match like exercises; ambiguous → candidates returned, nothing saved; habit list in the coach system prompt. Coach only. Each AI request spends free-tier quota (E15). |
| R11 | `created_at: datetime` | Project rules. | `timestamptz`; day buckets in APP_TZ via `timeutils`. |
| R12 | Status endpoint per date | Day switching, month grid, charts and offline ticking would each need a round trip. | One board query (habits + done dates since the earliest start) that the client derives everything from, so ticks are instant and work offline. Logic mirrored in `services/habits.py` (AI tools, tests) and `lib/habits.ts` (UI). |

## New idea: auto-completion from the app's own data (decision H2)
Habits may carry an `auto_rule` evaluated live at read time (not stored, so late Strava syncs or edits are
reflected): finished gym workout, Strava activity, gym or Strava, steps ≥ N, sleep ≥ N h, weight logged,
protein ≥ daily target. A manual tick still works as an override (e.g. training without the watch).
"Cvičení" becomes "gym or Strava" automatically.

## Data model (migration 0012)
- `habits`: `id` int PK (created online, like exercises), `title`, `frequency` (`daily`/`weekly`), `weekly_target`
  int default 1, `skill` enum nullable, `points` int default 1, `is_bonus` bool, `auto_rule` enum nullable,
  `auto_threshold` float nullable, `sort_order` int, `start_date` date, `archived_at` timestamptz nullable,
  `created_at` timestamptz.
- `habit_logs`: `habit_id` FK (cascade) + `date`, PK on both, `created_at` timestamptz.
- Migration `0012` (tables + one-time seed).

## API (`/api/habits`, implemented in 6.1)
- `GET /api/habits/board?start=` → `{today, start, habits: [habit + done: [dates ticked by hand] + auto: {date: label}]}`;
  archived habits included for history; `start` defaults to the earliest `start_date`.
- `PUT /api/habits/{id}/days/{date}` `{done}` — idempotent, offline-queued. Rejects days more than 1 day ahead; ticking a
  day before `start_date` moves `start_date` back.
- `POST /api/habits` (appended at the end; daily forces `weekly_target` 1, weekly forces `is_bonus` false, the threshold
  is kept only for steps / sleep / protein), `PATCH /api/habits/{id}` (incl. `archived: true|false`),
  `PUT /api/habits/order` `{ids}` (every habit once), `DELETE /api/habits/{id}` (hard delete with history).
- Auto rules (`services/habits.py`): gym = workout with a completed set; activity = any but `Walk`; steps default 10 000;
  sleep default 7 h; protein = threshold or the nutrition profile target (none → never auto).
- Coach tools (6.2): `get_habit_summary(days=30)` (rate, current/best streak, weekday pattern, routine-week streak),
  `set_habits_done(...)`.

## UI (decision H1)
- New tab **Rutina** with a Den / Měsíc switch, plus a compact "Dnešní rutina" card at the top of Přehled showing
  only what is left today.
- **Den**: day switcher (also swipe), week strip with mini rings (tap = jump to day), hero ring (%, done/total,
  points + bonus, routine-week streak), sections Denní / Bonus / Tento týden with 60 px tap rows, skill dot, flame
  streak, auto badge ("Strava · Dlouhý běh 18,2 km"), weekly rows with "hotovo čt" and an n/target count.
- **Měsíc**: stat tiles, calendar heatmap (sequential emerald, today outlined), habit × day matrix (14 days,
  scrolls), daily % bars + 7-day average line, per-habit success bars, weekday pattern, weekly tasks × 8 weeks.
- **Edit mode**: drag reorder, archive, add/edit sheet (name, daily/weekly, ×/week, skill, points, bonus, auto rule).
- Small celebration on a perfect day. Persisted query key versioned from day one.

## Decisions (answered 2026-10-18 → E20)
- **H1** Navigation → **6th tab "Rutina" + Přehled card**.
- **H2** Auto-completion rules → **in v1**.
- **H3** → **weekly targets and points + bonus**.
- **H4** Seed → **the user's sheet list in Czech**.

## RPG layer — accepted concept (E22, 2026-10-18)
**Binding for the implementation** (user: "take this as the correct concept to implement by"). Numbers marked
*(tune)* are starting values to adjust during implementation; the rules themselves are decided.

### Principles
- **Hard mode, no softening:** XP can go down and **the level can drop** (no level floor).
- **No streak-saving tokens** (no "streak freeze").
- **Every XP change has a visible reason:** an XP history lists each gain and penalty with its cause, e.g.
  "−80 XP: týden 12.–18. 10. splněn na 52 % (pod 60 %)".
- **Forgiveness: 1 day per calendar month.** The first missed (below-threshold) day of each month is forgiven:
  it triggers no day penalty, is left out of the week's routine %, and does not break daily streaks. Shown in the
  history as "odpuštěný den".
- **Pause (safeguard):** a manual "pauza" (sick, holiday) with a start and end; paused days count for nothing:
  no XP, no penalties, no effect on streaks or the week %. Shown as a pause period in the history.
- XP comes from history (habit logs, workouts, runs, meals, steps, sleep), so the level exists from day one.
  Penalties need the same determinism: a recomputable XP ledger (reason, date, amount, source) rather than
  hand-edited totals. Storage to decide at implementation (live computation vs. materialized ledger).

### Character and XP
- Level + XP bar on Přehled and Rutina; titles per level (Učeň → Vytrvalec → Maratonec → …).
- Gains *(tune)*: habit = points × 10 XP (bonus too); perfect day +50; working set in the gym 2; PR +50;
  running 5 XP/km, extra for a long run / planned quality session; protein target met, full day of food logged,
  sleep ≥ 7 h.
- Level curve: fast at first, slower later.

### Skills
Each with its own level and bar, fed by habit areas and real data: Síla (gym tonnage, PRs), Výdrž (km, long runs,
EF), Výživa (protein, food logged, diet), Disciplína (daily routine, streaks), Mysl (Anki, learning, new things),
Domov (cleaning). Radar chart of the skills.

### Streaks
- Routine-week streak (week counts at ≥ 60 % of the daily routine; already computed) and per-habit streaks.
- XP multiplier from the routine-week streak *(tune: +10 % per 2 weeks, max ×1.5)*.
- Personal best streaks per habit.

### Penalties (hard mode)
- **Week below 60 %:** the multiplier drops back to ×1.0 and the week's XP is cut *(tune: −10 % of that week's
  XP, at least −100 XP)*.
- **Day below 30 % of the routine:** −20 XP *(tune)* (the monthly forgiven day excepted).
- **Tired (debuff):** after a week below 60 %, the next week earns XP ×0.8 until that week reaches 60 %.
- **Cursed habit:** a habit missed 3× in a week is "cursed" the next week: done = double XP, missed again =
  a penalty *(tune)*.
- **Rusting skill:** a skill not fed for 14 days rusts (greyed bar); from 3 weeks it loses skill XP and its level
  can drop.
- **Boss heals:** a skipped planned run gives the marathon boss HP back (remaining planned km grow).
- **Quest failed:** an unfinished weekly quest stays in the history as failed, no reward.
- The total XP can fall across a level boundary: the level drops, with the reason shown.

### Bosses
- Marathon 2. 5. 2027 (HP = training km left in the RunningCoach plan); half marathon 3. 4. 2027 as a mini-boss.
- A defeated boss is stored with the race result as a trophy.

### Weekly quests
Generated each Monday from real plans (km from the plan, gym sessions, a neglected muscle group, full-flat clean,
Anki days), each with an XP reward and a bonus for all of them.

### Badges
Perfect day / week, 30 days creatine, 100 / 250 workouts, 1 000 km a year, first marathon, 5 km PR, …; locked
badges shown greyed.

### Coach as game master
Sunday summary in RPG tone (XP, quests, penalties and why, what is neglected, advice), data via tools as always.

### Small touches
Level-up animation, boss-defeat confetti, XP history chart by week.

### Implementation order
1. XP ledger + character level + titles + XP history with reasons (incl. penalties, forgiveness, pause).
2. Skills + radar + rusting.
3. Bosses (marathon).
4. Weekly quests + badges.
5. Debuffs (tired, cursed), game-master summary, animations.
