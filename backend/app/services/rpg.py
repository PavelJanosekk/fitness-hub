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
from app.services import habits as hs
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


@dataclass
class Ledger:
    entries: list[XpEntry] = field(default_factory=list)
    total: int = 0
    week_streak: int = 0  # qualifying routine weeks in a row, as of today
    multiplier: float = 1.0  # in effect this week
    paused_today: bool = False
    forgiven: set[dt.date] = field(default_factory=set)


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

    # Habits: daily ticks per day in one entry; a weekly habit when the week's target is reached
    daily: dict[dt.date, list[tuple[str, int]]] = defaultdict(list)
    for item in board:
        habit = item.habit
        if habit.frequency == HabitFrequency.daily:
            for day in item.done:
                if day <= on and hs.is_active(habit, day):
                    daily[day].append((habit.title, habit.points * HABIT_XP))
            continue
        by_week: dict[dt.date, list[dt.date]] = defaultdict(list)
        for day in sorted(d for d in item.done if d <= on):
            by_week[hs.week_start(day)].append(day)
        for days in by_week.values():
            if len(days) >= habit.weekly_target:
                reached = days[habit.weekly_target - 1]
                gains[reached].append(
                    XpEntry(reached, habit.points * WEEKLY_HABIT_XP, "weekly_habit", f"Týdenní úkol: {habit.title}")
                )
    for day, ticks in daily.items():
        names = ", ".join(title for title, _ in ticks)
        gains[day].append(XpEntry(day, sum(xp for _, xp in ticks), "habits", f"Návyky: {names}"))
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
    ledger = Ledger(forgiven=forgiven, paused_today=on in paused)
    if not gains and not board:
        return ledger

    routine_start = min((d.habit.start_date for d in board), default=None)
    first_day = min([*gains.keys(), *([routine_start] if routine_start else [])])
    streak, week_xp, total = 0, 0, 0
    multiplier = 1.0
    level = level_of(0)
    day = first_day
    while day <= on:
        if day.weekday() == 0:
            multiplier = multiplier_for(streak)
        entries: list[XpEntry] = []
        if day in paused:
            if day - dt.timedelta(days=1) not in paused:
                entries.append(XpEntry(day, 0, "pause", "Pauza: dny se nepočítají"))
        else:
            day_gains = gains.get(day, [])
            entries.extend(day_gains)
            base = sum(e.amount for e in day_gains)
            if base > 0 and multiplier > 1:
                bonus = round(base * (multiplier - 1))
                entries.append(XpEntry(day, bonus, "multiplier", f"Násobič týdenní série {_mult(multiplier)}"))
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
            week_xp = 0

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
    return ledger
