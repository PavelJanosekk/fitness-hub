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

## RPG layer — ideas for later (not accepted)
Everything below can be computed retroactively from habit logs + existing workouts, runs, meals and steps, so v1
only has to store `points` and `skill`.
- Character level + XP bar; titles per level.
- Skills with levels: Síla (gym tonnage, PRs), Výdrž (km, long runs), Výživa (protein target, food logged),
  Domov, Disciplína, Mysl.
- Streaks: routine-week streak (week counts at ≥ 60 % daily completion) with an XP multiplier; streak freezes
  earned over time (a sick week does not reset it).
- Weekly quests generated from real plans (km from the RunningCoach plan, gym sessions, full-flat clean).
- Bosses: the marathon (2. 5. 2027) with HP = remaining planned training km; the half marathon as a mini-boss.
- Badges (perfect day, 30 days creatine, 100 workouts, first marathon).
- The coach as "game master" for a weekly review.
