"""RPG layer, step 7.1 (E22, docs/habits-module-spec.md "RPG layer — accepted concept"): the XP ledger.

The ledger is computed live from history (habits, workouts, PRs, runs, meals, sleep, pauses), so a late tick or a
Strava sync rewrites it consistently. Hard mode: penalties can take the total down and the level with it; every
change is an entry with a Czech reason. Values marked (tune) are starting points from the concept.

Day by day from the first data point to today:
- gains: habits (points x 10), a weekly habit when its target is reached (points x 20), perfect day +50, gym working
  set 2, PR +50, run 5 per km (+25 for a long run), protein target +20, food logged +10, sleep >= 7 h +10;
- the routine-week streak multiplier (+10 % per 2 qualifying weeks, max x1.5) adds its bonus as its own entry;
- a finished day below 30 % of the routine: -20; the month's first missed day (< 60 %) is forgiven instead;
- a finished week below 60 %: -max(100, 10 % of that week's XP) and the streak (multiplier) resets;
- paused days count for nothing.

Debuffs (7.5):
- tired: the week after a week below 60 % earns x0.8 (the cut is its own entry) until that week's routine, counted
  so far, is back at 60 %;
- cursed habit: a daily routine habit missed 3+ times in a finished week is cursed the next week: every day it is
  done pays its XP again (double), every finished day it is missed costs its XP.

Skills (7.2): every entry is attributed to skills (`XpEntry.skills`). A skill that gained nothing for
RUST_START_DAYS rusts: from RUST_LOSS_DAYS on it loses RUST_SHARE of its XP every week (a ledger entry, so the total
and the level drop too); paused days and days before the routine's first day don't count as idle.

Bucket list (E36, services/bucket.py): completed items, steps and the yearly bonus feed the Dobrodružství skill. They
also count on paused days (a holiday is when bucket-list things happen), and Dobrodružství never rusts.
Dovednosti (E37, services/abilities.py): the first entry of a new dovednost pays Mysl, also on a paused day.
Side quests (E45, services/side_quests.py): a completed quest pays by duration to its category's skill, also on a
paused day.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models.body import DailyMetric
from app.models.gym import Workout, WorkoutSet
from app.models.habits import HabitFrequency
from app.models.nutrition import MealLog, NutritionProfile
from app.models.rpg import RpgPause
from app.models.running import Activity
from app.services import abilities as ab
from app.services import bucket as bk
from app.services import habits as hs
from app.services import quests as qs
from app.services import side_quests as sq
from app.services.metrics import intake_by_day
from app.services.run_analysis import RUN_TYPES
from app.services.workouts import WORKING_SET, personal_records
from app.timeutils import local_date, today

# (tune) values from the accepted concept
HABIT_XP = 10  # x habit points
WEEKLY_HABIT_XP = 20  # x habit points, when the week's target is reached
PERFECT_DAY_XP = 50
GYM_SET_XP = 2
PR_XP = 50
RUN_KM_XP = 5
LONG_RUN_KM = 15
LONG_RUN_XP = 25
PROTEIN_XP = 20
FOOD_LOGGED_XP = 10
SLEEP_HOURS = 7.0
SLEEP_XP = 10
DAY_PENALTY_PCT = 30
DAY_PENALTY_XP = 20
WEEK_PENALTY_MIN = 100
WEEK_PENALTY_SHARE = 0.10
MULTIPLIER_STEP = 0.1  # per 2 qualifying weeks in a row
MULTIPLIER_MAX = 1.5
TIRED_FACTOR = 0.8
CURSE_MISSES = 3
RUST_START_DAYS = 14  # idle days until a skill shows as rusting
RUST_LOSS_DAYS = 21  # idle days until it starts losing XP, then every further week
RUST_SHARE = 0.10
RUST_MIN = 20

SKILLS = [
    ("strength", "Síla", "gym a osobní rekordy"),
    ("endurance", "Výdrž", "běhy, dlouhé běhy"),
    ("nutrition", "Výživa", "jídlo, bílkoviny, návyky Výživa"),
    ("discipline", "Disciplína", "rutina, perfektní dny, spánek"),
    ("mind", "Mysl", "návyky Mysl"),
    ("home", "Domov", "návyky Domov"),
    ("adventure", "Dobrodružství", "bucket list, side questy"),
]
NO_RUST = {"adventure"}  # fed by rare events, not by training
SKILL_NAMES = {key: name for key, name, _ in SKILLS}
KIND_SKILL = {
    "gym": "strength",
    "pr": "strength",
    "run": "endurance",
    "long_run": "endurance",
    "food": "nutrition",
    "protein": "nutrition",
    "sleep": "discipline",
    "perfect_day": "discipline",
    "multiplier": "discipline",
    "day_penalty": "discipline",
    "week_penalty": "discipline",
    "tired": "discipline",
}
HABIT_SKILL_NAMES = {"body": "Tělo", "nutrition": "Výživa", "home": "Domov", "discipline": "Disciplína", "mind": "Mysl"}
BUCKET_KINDS = {"bucket", "bucket_goal", "bucket_step", "bucket_year"}
# Rare events that also count on paused days
EVENT_KINDS = BUCKET_KINDS | {"ability_new", "side_quest"}
TITLES = [
    (1, "Učeň"),
    (5, "Poutník"),
    (10, "Vytrvalec"),
    (15, "Maratonec"),
    (20, "Železný"),
    (25, "Mistr"),
    (30, "Legenda"),
]


@dataclass
class XpEntry:
    date: dt.date
    amount: int
    kind: str
    text: str
    skills: dict[str, int] = field(default_factory=dict)  # attribution of `amount` to skills


def habit_skills(habit_skill: str | None, amount: int) -> dict[str, int]:
    """Habit areas map to RPG skills; "body" habits (e.g. Cvičení) split between Síla and Výdrž."""
    if habit_skill == "body":
        return {"strength": amount // 2, "endurance": amount - amount // 2}
    return {habit_skill if habit_skill in SKILL_NAMES else "discipline": amount}


@dataclass
class SkillState:
    key: str
    xp: int = 0
    last_gain: dt.date | None = None
    idle_days: int = 0  # unpaused days since the last gain


@dataclass
class Ledger:
    entries: list[XpEntry] = field(default_factory=list)
    total: int = 0
    week_streak: int = 0  # qualifying routine weeks in a row, as of today
    multiplier: float = 1.0  # in effect this week
    paused_today: bool = False
    forgiven: set[dt.date] = field(default_factory=set)
    skills: dict[str, SkillState] = field(default_factory=dict)
    quests: list["qs.Quest"] = field(default_factory=list)  # this week's
    tired: bool = False  # the tired debuff is active today
    cursed: list[str] = field(default_factory=list)  # this week's cursed habits


# --- Levels ----------------------------------------------------------------------------------


def xp_to_next(level: int) -> int:
    """XP from `level` to `level + 1`: fast at first, slower later (tune)."""
    return round(100 * level**1.5)


def level_start(level: int) -> int:
    return sum(xp_to_next(n) for n in range(1, level))


def level_of(total: int) -> int:
    level = 1
    while total >= level_start(level + 1):
        level += 1
    return level


def skill_xp_to_next(level: int) -> int:
    """Skills level up on a flatter curve than the character (tune)."""
    return round(50 * level**1.5)


def skill_level_start(level: int) -> int:
    return sum(skill_xp_to_next(n) for n in range(1, level))


def skill_level_of(xp: int) -> int:
    level = 1
    while xp >= skill_level_start(level + 1):
        level += 1
    return level


def title_of(level: int) -> str:
    return [title for at, title in TITLES if level >= at][-1]


def next_title(level: int) -> tuple[int, str] | None:
    return next(((at, title) for at, title in TITLES if at > level), None)


def multiplier_for(streak: int) -> float:
    return round(min(MULTIPLIER_MAX, 1 + MULTIPLIER_STEP * (streak // 2)), 2)


def _km(meters: float) -> str:
    return f"{meters / 1000:.1f}".replace(".", ",")


def _mult(value: float) -> str:
    return f"×{value:.1f}".replace(".", ",")


# --- Ledger ----------------------------------------------------------------------------------


def _gains_by_day(session: Session, board: list[hs.HabitDays], on: dt.date) -> dict[dt.date, list[XpEntry]]:
    gains: dict[dt.date, list[XpEntry]] = defaultdict(list)

    # Habits: one entry per day and area; a weekly habit when the week's target is reached
    daily: dict[dt.date, dict[str | None, list[tuple[str, int]]]] = defaultdict(lambda: defaultdict(list))
    for item in board:
        habit = item.habit
        if habit.frequency == HabitFrequency.daily:
            for day in item.done:
                if day <= on and hs.is_active(habit, day):
                    daily[day][habit.skill].append((habit.title, habit.points * HABIT_XP))
            continue
        by_week: dict[dt.date, list[dt.date]] = defaultdict(list)
        for day in sorted(d for d in item.done if d <= on):
            by_week[hs.week_start(day)].append(day)
        for days in by_week.values():
            if len(days) >= habit.weekly_target:
                reached = days[habit.weekly_target - 1]
                xp = habit.points * WEEKLY_HABIT_XP
                text = f"Týdenní úkol: {habit.title}"
                gains[reached].append(XpEntry(reached, xp, "weekly_habit", text, habit_skills(habit.skill, xp)))
    for day, areas in daily.items():
        for area, ticks in areas.items():
            names = ", ".join(title for title, _ in ticks)
            label = f"Návyky ({HABIT_SKILL_NAMES[area]})" if area in HABIT_SKILL_NAMES else "Návyky"
            xp = sum(points for _, points in ticks)
            gains[day].append(XpEntry(day, xp, "habits", f"{label}: {names}", habit_skills(area, xp)))
        done, scheduled = hs.routine_day(board, day)
        if scheduled and done == scheduled:
            gains[day].append(XpEntry(day, PERFECT_DAY_XP, "perfect_day", "Perfektní den"))

    # Gym: working sets per workout, PRs
    rows = session.exec(
        select(Workout.id, Workout.started_at, Workout.name, WorkoutSet.id)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WORKING_SET)
    ).all()
    workouts: dict = {}
    for workout_id, started_at, name, _ in rows:
        entry = workouts.setdefault(workout_id, [local_date(started_at), name, 0])
        entry[2] += 1
    for day, name, sets in workouts.values():
        if day <= on:
            gains[day].append(XpEntry(day, sets * GYM_SET_XP, "gym", f"Gym: {name} · {sets} sérií"))
    for workout_id, records in personal_records(session).items():
        if workout_id not in workouts or workouts[workout_id][0] > on:
            continue
        day = workouts[workout_id][0]
        for record in records:
            gains[day].append(XpEntry(day, PR_XP, "pr", f"Osobní rekord: {record.name}"))

    # Runs
    for activity in session.exec(select(Activity).where(col(Activity.activity_type).in_(RUN_TYPES))):
        day = local_date(activity.start_time)
        if day > on:
            continue
        km = activity.distance_meters / 1000
        gains[day].append(XpEntry(day, round(km * RUN_KM_XP), "run", f"Běh {_km(activity.distance_meters)} km"))
        if km >= LONG_RUN_KM:
            gains[day].append(XpEntry(day, LONG_RUN_XP, "long_run", "Dlouhý běh"))

    # Food, protein, sleep
    for day in session.exec(select(MealLog.logged_date).distinct()).all():
        if day <= on:
            gains[day].append(XpEntry(day, FOOD_LOGGED_XP, "food", "Zapsané jídlo"))
    profile = session.get(NutritionProfile, 1)
    if profile and profile.protein_target_g:
        first_meal = session.exec(select(MealLog.logged_date).order_by(col(MealLog.logged_date)).limit(1)).first()
        if first_meal:
            for day, (_, protein, _, _) in intake_by_day(session, first_meal, on).items():
                if protein is not None and protein >= profile.protein_target_g:
                    gains[day].append(XpEntry(day, PROTEIN_XP, "protein", f"Bílkoviny {round(protein)} g (cíl splněn)"))
    for metric in session.exec(select(DailyMetric).where(col(DailyMetric.sleep_hours) >= SLEEP_HOURS)):
        if metric.date <= on:
            hours = f"{metric.sleep_hours:.1f}".replace(".", ",")
            gains[metric.date].append(XpEntry(metric.date, SLEEP_XP, "sleep", f"Spánek {hours} h"))
    return gains


def _track_skills(
    skills: dict[str, SkillState], entries: list[XpEntry], day: dt.date, rust_from: dt.date | None
) -> list[XpEntry]:
    """Credit the day's entries to skills, then let idle skills rust. Returns the rust entries.

    Like every penalty, rust only exists once the RPG does (`rust_from` = the routine's first day): idle days before
    it are not counted, so old breaks in the training history never cost anything.
    """
    gained = _credit_skills(skills, entries, day)
    rust: list[XpEntry] = []
    for key, state in skills.items():
        if key in gained:
            continue
        if state.last_gain is None or rust_from is None or day < rust_from or key in NO_RUST:
            continue  # never trained, or before the RPG existed: nothing to rust
        state.idle_days += 1
        idle = state.idle_days
        if idle >= RUST_LOSS_DAYS and (idle - RUST_LOSS_DAYS) % 7 == 0 and state.xp > 0:
            loss = min(state.xp, max(RUST_MIN, round(state.xp * RUST_SHARE)))
            state.xp -= loss
            text = f"Rezavění: {SKILL_NAMES[key]} ({idle} dní bez XP)"
            rust.append(XpEntry(day, -loss, "rust", text, {key: -loss}))
    return rust


def _credit_skills(skills: dict[str, SkillState], entries: list[XpEntry], day: dt.date) -> set[str]:
    """Adds the entries' XP to their skills; returns the skills that gained."""
    gained: set[str] = set()
    for entry in entries:
        attribution = entry.skills or ({KIND_SKILL[entry.kind]: entry.amount} if entry.kind in KIND_SKILL else {})
        entry.skills = attribution
        for key, amount in attribution.items():
            state = skills.setdefault(key, SkillState(key))
            state.xp += amount
            if amount > 0:
                gained.add(key)
                state.last_gain, state.idle_days = day, 0
    return gained


def quest_skills(quest: "qs.Quest") -> dict[str, int]:
    return {quest.skill: quest.xp} if quest.skill else habit_skills(quest.habit_skill, quest.xp)


def _quest_entries(
    session: Session,
    board: list[hs.HabitDays],
    gains: dict[dt.date, list[XpEntry]],
    routine_start: dt.date,
    on: dt.date,
) -> list["qs.Quest"]:
    """Adds every week's quest rewards / failures to `gains`; returns this week's quests."""
    first = hs.week_start(routine_start)
    history = qs.load_history(session, first - dt.timedelta(days=qs.LOOKBACK_DAYS), on)
    week, current = first, []
    while week <= on:
        skill_xp: dict[str, int] = defaultdict(int)
        for back in range(1, qs.LOOKBACK_DAYS + 1):
            for entry in gains.get(week - dt.timedelta(days=back), []):
                for skill, amount in entry.skills.items():
                    skill_xp[skill] += amount
        quests = qs.week_quests(history, board, week, on, skill_xp)
        for quest in quests:
            if quest.done_on:
                text = f"Výprava splněna: {quest.title}"
                gains[quest.done_on].append(XpEntry(quest.done_on, quest.xp, "quest", text, quest_skills(quest)))
        if quests and all(q.done_on for q in quests):
            last = max(q.done_on for q in quests if q.done_on)
            bonus = XpEntry(
                last, qs.ALL_QUESTS_XP, "quests_all", "Všechny výpravy týdne splněny", {"discipline": qs.ALL_QUESTS_XP}
            )
            gains[last].append(bonus)
        sunday = week + dt.timedelta(days=6)
        if sunday < on:
            for quest in quests:
                if not quest.done_on:
                    progress = f"{quest.progress:g}/{quest.target:g} {quest.unit}".replace(".", ",")
                    gains[sunday].append(
                        XpEntry(sunday, 0, "quest_failed", f"Výprava nesplněna: {quest.title} ({progress})")
                    )
        current = quests
        week += dt.timedelta(weeks=1)
    return current


def build_ledger(session: Session, on: dt.date | None = None) -> Ledger:
    on = on or today()
    board = hs.load_board(session, end=on)
    if board:
        paused, forgiven = board[0].paused, board[0].forgiven
    else:
        pauses = session.exec(select(RpgPause.start_date, RpgPause.end_date)).all()
        first = min((p[0] for p in pauses), default=on)
        paused, forgiven = hs.exceptions([], list(pauses), first, on)
    gains = _gains_by_day(session, board, on)
    for gain in bk.gains(bk.load(session, on), on):
        gains[gain.date].append(XpEntry(gain.date, gain.amount, gain.kind, gain.text, {bk.SKILL: gain.amount}))
    for side in sq.gains(sq.load(session, on)):
        gains[side.date].append(XpEntry(side.date, side.amount, side.kind, side.text, {side.skill: side.amount}))
    for gain in ab.gains(ab.load(session, on), on):
        gains[gain.date].append(XpEntry(gain.date, gain.amount, gain.kind, gain.text, {ab.SKILL: gain.amount}))
    ledger = Ledger(forgiven=forgiven, paused_today=on in paused)
    if not gains and not board:
        return ledger

    routine_start = min((d.habit.start_date for d in board), default=None)
    if routine_start:
        ledger.quests = _quest_entries(session, board, gains, routine_start, on)
    first_day = min([*gains.keys(), *([routine_start] if routine_start else [])])
    streak, week_xp, total = 0, 0, 0
    multiplier = 1.0
    level = level_of(0)
    failed_last_week, tired = False, False
    cursed: list[hs.HabitDays] = []
    day = first_day
    while day <= on:
        entries: list[XpEntry] = []
        if day.weekday() == 0:
            multiplier = multiplier_for(streak)
            tired, failed_last_week = failed_last_week, False
            cursed = _cursed(board, day, skip=paused | forgiven)
            if tired:
                entries.append(
                    XpEntry(day, 0, "tired", "Únava: po týdnu pod 60 % jde XP ×0,8, dokud nebude týden na 60 %")
                )
            for item in cursed:
                text = f"Prokletý návyk: {item.habit.title} (minulý týden vynechán {CURSE_MISSES}× a víc)"
                entries.append(XpEntry(day, 0, "curse", text))
        if day in paused:
            if day - dt.timedelta(days=1) not in paused:
                entries.append(XpEntry(day, 0, "pause", "Pauza: dny se nepočítají"))
            entries.extend(e for e in gains.get(day, []) if e.kind in EVENT_KINDS)
        else:
            day_gains = gains.get(day, [])
            entries.extend(day_gains)
            base = sum(e.amount for e in day_gains)
            if base > 0 and multiplier > 1:
                bonus = round(base * (multiplier - 1))
                entries.append(XpEntry(day, bonus, "multiplier", f"Násobič týdenní série {_mult(multiplier)}"))
            if base > 0 and tired:
                cut = round(base * (1 - TIRED_FACTOR))
                entries.append(XpEntry(day, -cut, "tired", f"Únava ×{TIRED_FACTOR:.1f}".replace(".", ",")))
            for item in cursed:
                xp = item.habit.points * HABIT_XP
                if day in item.done:
                    text = f"Prokletý návyk splněn: {item.habit.title} (XP ×2)"
                    entries.append(XpEntry(day, xp, "curse_done", text, habit_skills(item.habit.skill, xp)))
                elif day < on and day not in forgiven and hs.is_active(item.habit, day):
                    text = f"Prokletý návyk vynechán: {item.habit.title}"
                    entries.append(XpEntry(day, -xp, "curse_missed", text, habit_skills(item.habit.skill, -xp)))
            if tired:
                so_far = hs.routine_week_pct(board, hs.week_start(day), day)
                if so_far is not None and so_far >= hs.ROUTINE_WEEK_PCT:
                    tired = False  # recovered: from tomorrow on
                    entries.append(XpEntry(day, 0, "tired_end", f"Únava pryč: týden zatím na {round(so_far)} %"))
            done, scheduled = hs.routine_day(board, day)
            if day < on and scheduled:
                pct = done / scheduled * 100
                if day in forgiven:
                    text = f"Odpuštěný den: rutina na {round(pct)} % (1× za měsíc)"
                    entries.append(XpEntry(day, 0, "forgiven", text))
                elif pct < DAY_PENALTY_PCT:
                    text = f"Den pod {DAY_PENALTY_PCT} % rutiny ({round(pct)} %)"
                    entries.append(XpEntry(day, -DAY_PENALTY_XP, "day_penalty", text))
        week_xp += sum(e.amount for e in entries if e.amount > 0)

        if day.weekday() == 6 and day < on:
            pct = hs.routine_week_pct(board, hs.week_start(day), day) if board else None
            if pct is not None:
                span = f"{hs.week_start(day).day}.–{day.day}. {day.month}."
                if pct >= hs.ROUTINE_WEEK_PCT:
                    streak += 1
                    text = f"Týden {span} splněn na {round(pct)} % · série {streak}"
                    if multiplier_for(streak) > multiplier:
                        text += f", násobič {_mult(multiplier_for(streak))} od pondělí"
                    entries.append(XpEntry(day, 0, "week_ok", text))
                else:
                    penalty = max(WEEK_PENALTY_MIN, round(week_xp * WEEK_PENALTY_SHARE))
                    text = f"Týden {span} splněn na {round(pct)} % (pod {hs.ROUTINE_WEEK_PCT} %)"
                    if streak:
                        text += f", série {streak} končí"
                    entries.append(XpEntry(day, -penalty, "week_penalty", text))
                    streak = 0
                    failed_last_week = True
            week_xp = 0

        if day not in paused:
            entries.extend(_track_skills(ledger.skills, entries, day, routine_start))
        else:
            _credit_skills(ledger.skills, entries, day)

        total += sum(e.amount for e in entries)
        new_level = level_of(total)
        if new_level != level:
            kind, verb = ("level_up", "Postup") if new_level > level else ("level_down", "Pokles")
            entries.append(XpEntry(day, 0, kind, f"{verb} na level {new_level} · {title_of(new_level)}"))
            level = new_level
        ledger.entries.extend(entries)
        day += dt.timedelta(days=1)

    ledger.total = total
    ledger.week_streak = streak
    ledger.multiplier = multiplier
    ledger.tired = tired and on not in paused
    ledger.cursed = [item.habit.title for item in cursed]
    return ledger


def _cursed(board: list[hs.HabitDays], monday: dt.date, skip: set[dt.date]) -> list[hs.HabitDays]:
    """Daily routine habits missed CURSE_MISSES+ times in the week before `monday` (skipped days don't count)."""
    week = [monday - dt.timedelta(days=7 - i) for i in range(7)]
    return [
        item
        for item in board
        if item.habit.frequency == HabitFrequency.daily
        and not item.habit.is_bonus
        and item.habit.archived_at is None
        and sum(1 for d in week if hs.is_active(item.habit, d) and d not in item.done and d not in skip) >= CURSE_MISSES
    ]
