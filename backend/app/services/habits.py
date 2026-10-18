"""Habit tracker logic (E20, docs/habits-module-spec.md): auto rules, day/week status, streaks and rates.

The frontend derives the same numbers in `lib/habits.ts` so a tick shows instantly and works offline; keep the
rules of both in sync:
- a habit counts from its `start_date` and stops counting on the day it is archived;
- a daily streak ends today if today is done, else yesterday (an unticked today does not break it);
- a weekly habit is met in an ISO week with at least `weekly_target` done days; its streak counts met weeks the
  same way (the current week only once it is met);
- the routine of a day = active non-bonus daily habits; bonus habits only add points;
- a routine week counts toward the routine streak at >= ROUTINE_WEEK_PCT % of its scheduled daily ticks;
- skipped days (a pause, or the one forgiven missed day per month, E22) count for nothing: they neither break nor
  extend a streak and are left out of rates and the week %; a fully paused week is skipped the same way.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.body import DailyMetric
from app.models.gym import Workout, WorkoutSet
from app.models.habits import AutoRule, Habit, HabitFrequency, HabitLog
from app.models.nutrition import NutritionProfile
from app.models.rpg import RpgPause
from app.models.running import Activity
from app.services.metrics import intake_by_day
from app.timeutils import day_bounds, local_date, today

ROUTINE_WEEK_PCT = 60
DEFAULT_THRESHOLDS = {AutoRule.steps: 10_000.0, AutoRule.sleep: 7.0}
EXCLUDED_ACTIVITY_TYPES = ("Walk",)
ACTIVITY_LABELS = {
    "Run": "Běh",
    "TrailRun": "Trail",
    "VirtualRun": "Běh",
    "Ride": "Kolo",
    "VirtualRide": "Kolo",
    "Swim": "Plavání",
    "Hike": "Túra",
    "WeightTraining": "Posilování",
}
MIN_SIMILARITY = 0.3


def week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _decimal(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


@dataclass
class HabitDays:
    """A habit with the days it was done: ticked by hand, or completed by its auto rule (day -> what did it)."""

    habit: Habit
    manual: set[dt.date] = field(default_factory=set)
    auto: dict[dt.date, str] = field(default_factory=dict)
    paused: set[dt.date] = field(default_factory=set)  # shared by every habit of one board
    forgiven: set[dt.date] = field(default_factory=set)  # shared too: one missed day per month

    @property
    def skip(self) -> set[dt.date]:
        return self.paused | self.forgiven

    @property
    def done(self) -> set[dt.date]:
        return self.manual | self.auto.keys()


# --- Auto rules ------------------------------------------------------------------------------


def _gym_days(session: Session, lo: dt.datetime, hi: dt.datetime) -> dict[dt.date, str]:
    has_sets = select(WorkoutSet.workout_id).where(col(WorkoutSet.completed))
    rows = session.exec(
        select(Workout.started_at, Workout.name)
        .where(col(Workout.started_at) >= lo, col(Workout.started_at) < hi, col(Workout.id).in_(has_sets))
        .order_by(col(Workout.started_at))
    )
    days: dict[dt.date, str] = {}
    for started_at, name in rows:
        days.setdefault(local_date(started_at), f"Gym · {name}")
    return days


def _activity_days(session: Session, lo: dt.datetime, hi: dt.datetime) -> dict[dt.date, str]:
    rows = session.exec(
        select(Activity)
        .where(
            col(Activity.start_time) >= lo,
            col(Activity.start_time) < hi,
            col(Activity.activity_type).not_in(EXCLUDED_ACTIVITY_TYPES),
        )
        .order_by(col(Activity.start_time))
    )
    days: dict[dt.date, str] = {}
    for activity in rows:
        kind = ACTIVITY_LABELS.get(activity.activity_type, activity.activity_type)
        if activity.distance_meters >= 100:
            label = f"{kind} {_decimal(activity.distance_meters / 1000)} km"
        else:
            label = f"{kind} {round(activity.duration_seconds / 60)} min"
        days.setdefault(local_date(activity.start_time), label)
    return days


def _metric_days(session: Session, start: dt.date, end: dt.date, rule: AutoRule, threshold: float | None):
    days: dict[dt.date, str] = {}
    for metric in session.exec(select(DailyMetric).where(col(DailyMetric.date).between(start, end))):
        if rule == AutoRule.steps and metric.steps is not None and metric.steps >= (threshold or 0):
            days[metric.date] = f"{metric.steps:,} kroků".replace(",", " ")
        elif rule == AutoRule.sleep and metric.sleep_hours is not None and metric.sleep_hours >= (threshold or 0):
            days[metric.date] = f"{_decimal(metric.sleep_hours)} h spánku"
        elif rule == AutoRule.weight_logged and metric.weight_kg is not None:
            days[metric.date] = f"{_decimal(metric.weight_kg)} kg"
    return days


def _protein_days(session: Session, start: dt.date, end: dt.date, threshold: float | None) -> dict[dt.date, str]:
    if threshold is None:
        profile = session.get(NutritionProfile, 1)
        threshold = profile.protein_target_g if profile else None
    if not threshold:
        return {}
    return {
        day: f"{round(protein)} g bílkovin"
        for day, (_, protein, _, _) in intake_by_day(session, start, end).items()
        if protein is not None and protein >= threshold
    }


def auto_days(
    session: Session, rule: AutoRule, threshold: float | None, start: dt.date, end: dt.date
) -> dict[dt.date, str]:
    """Days in [start, end] the rule is satisfied, each with a short Czech label of what satisfied it."""
    threshold = threshold if threshold is not None else DEFAULT_THRESHOLDS.get(rule)
    lo, _ = day_bounds(start)
    _, hi = day_bounds(end)
    match rule:
        case AutoRule.gym_workout:
            return _gym_days(session, lo, hi)
        case AutoRule.activity:
            return _activity_days(session, lo, hi)
        case AutoRule.gym_or_activity:
            return _activity_days(session, lo, hi) | _gym_days(session, lo, hi)
        case AutoRule.protein:
            return _protein_days(session, start, end, threshold)
        case _:
            return _metric_days(session, start, end, rule, threshold)


# --- Board -----------------------------------------------------------------------------------


def load_board(
    session: Session, start: dt.date | None = None, end: dt.date | None = None, *, archived: bool = True
) -> list[HabitDays]:
    """All habits in their order with their done days in [start, end] (default: since the earliest habit)."""
    end = end or today()
    query = select(Habit).order_by(col(Habit.position), col(Habit.id))
    if not archived:
        query = query.where(col(Habit.archived_at).is_(None))
    habits = session.exec(query).all()
    if not habits:
        return []
    start = start or min(h.start_date for h in habits)
    board = {h.id: HabitDays(h) for h in habits}
    for log in session.exec(select(HabitLog).where(col(HabitLog.date).between(start, end))):
        if log.habit_id in board:
            board[log.habit_id].manual.add(log.date)
    rule_cache: dict[tuple[str, float | None], dict[dt.date, str]] = {}
    for days in board.values():
        habit = days.habit
        if habit.auto_rule:
            key = (habit.auto_rule, habit.auto_threshold)
            if key not in rule_cache:
                rule_cache[key] = auto_days(session, AutoRule(habit.auto_rule), habit.auto_threshold, start, end)
            days.auto = {d: label for d, label in rule_cache[key].items() if is_active(habit, d)}
    result = list(board.values())
    pauses = session.exec(select(RpgPause.start_date, RpgPause.end_date)).all()
    paused, forgiven = exceptions(result, list(pauses), start, end)
    for days in result:
        days.paused, days.forgiven = paused, forgiven
    return result


def exceptions(
    board: list[HabitDays], pauses: list[tuple[dt.date, dt.date | None]], start: dt.date, on: dt.date
) -> tuple[set[dt.date], set[dt.date]]:
    """Paused days in [start, on], and the forgiven day of each month: its first finished, unpaused day with the
    routine below ROUTINE_WEEK_PCT % (today is still open, so it is never forgiven)."""
    paused: set[dt.date] = set()
    for first, last in pauses:
        day = max(first, start)
        while day <= min(last or on, on):
            paused.add(day)
            day += dt.timedelta(days=1)
    forgiven: set[dt.date] = set()
    months: set[tuple[int, int]] = set()
    day = start
    while day < on:
        if day not in paused and (day.year, day.month) not in months:
            done, scheduled = routine_day(board, day)
            if scheduled and done / scheduled * 100 < ROUTINE_WEEK_PCT:
                forgiven.add(day)
                months.add((day.year, day.month))
        day += dt.timedelta(days=1)
    return paused, forgiven


def set_day(session: Session, habit: Habit, day: dt.date, done: bool) -> None:
    """Idempotent: the same call twice leaves the same state (offline replays, double taps)."""
    log = session.get(HabitLog, (habit.id, day))
    if done and log is None:
        session.add(HabitLog(habit_id=habit.id, date=day))
    elif not done and log is not None:
        session.delete(log)
    session.commit()


# --- Status, streaks, rates ------------------------------------------------------------------


def archived_on(habit: Habit) -> dt.date | None:
    return local_date(habit.archived_at) if habit.archived_at else None


def is_active(habit: Habit, day: dt.date) -> bool:
    archived = archived_on(habit)
    return day >= habit.start_date and (archived is None or day < archived)


def week_count(done: set[dt.date], monday: dt.date) -> int:
    return sum(1 for offset in range(7) if monday + dt.timedelta(days=offset) in done)


def _week_skipped(skip: set[dt.date], monday: dt.date) -> bool:
    return all(monday + dt.timedelta(days=offset) in skip for offset in range(7))


def current_streak(days: HabitDays, on: dt.date) -> int:
    """Consecutive done days (daily) or met weeks (weekly) up to `on`; an unfinished day/week does not break it,
    skipped days (pause, forgiven) are stepped over."""
    habit, done, skip = days.habit, days.done, days.skip
    streak = 0
    if habit.frequency == HabitFrequency.weekly:
        week = week_start(on)
        if week_count(done, week) < habit.weekly_target:
            week -= dt.timedelta(weeks=1)
        while week >= week_start(habit.start_date):
            if week_count(done, week) >= habit.weekly_target:
                streak += 1
            elif not _week_skipped(skip, week):
                break
            week -= dt.timedelta(weeks=1)
        return streak
    day = on if on in done else on - dt.timedelta(days=1)
    while day >= habit.start_date:
        if day in done:
            streak += 1
        elif day not in skip:
            break
        day -= dt.timedelta(days=1)
    return streak


def best_streak(days: HabitDays, on: dt.date) -> int:
    habit, done, skip = days.habit, days.done, days.skip
    best = run = 0
    if habit.frequency == HabitFrequency.weekly:
        week = week_start(habit.start_date)
        while week <= week_start(on):
            if week_count(done, week) >= habit.weekly_target:
                run += 1
            elif not _week_skipped(skip, week):
                run = 0
            best = max(best, run)
            week += dt.timedelta(weeks=1)
        return best
    day = habit.start_date
    while day <= on:
        if day in done:
            run += 1
        elif day not in skip:
            run = 0
        best = max(best, run)
        day += dt.timedelta(days=1)
    return best


def completion(days: HabitDays, start: dt.date, end: dt.date) -> tuple[int, int]:
    """(done, scheduled) days for daily habits or met/elapsed weeks for weekly ones, while the habit was active.

    The current week only counts once it is met, so an ongoing week never drags the rate down; skipped days
    (and fully skipped weeks) only count when done anyway.
    """
    habit, done, skip = days.habit, days.done, days.skip
    if habit.frequency == HabitFrequency.weekly:
        met = scheduled = 0
        week = week_start(max(start, habit.start_date))
        while week <= end:
            if is_active(habit, max(week, habit.start_date)):
                is_met = week_count(done, week) >= habit.weekly_target
                if is_met or (week < week_start(end) and not _week_skipped(skip, week)):
                    scheduled += 1
                    met += is_met
            week += dt.timedelta(weeks=1)
        return met, scheduled
    active = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    active = [d for d in active if is_active(habit, d) and (d in done or d not in skip)]
    return sum(1 for d in active if d in done), len(active)


def routine_day(board: Iterable[HabitDays], day: dt.date) -> tuple[int, int]:
    """(done, scheduled) non-bonus daily habits of one day."""
    routine = [
        days
        for days in board
        if days.habit.frequency == HabitFrequency.daily and not days.habit.is_bonus and is_active(days.habit, day)
    ]
    return sum(1 for days in routine if day in days.done), len(routine)


def routine_week_pct(board: list[HabitDays], monday: dt.date, on: dt.date) -> float | None:
    """Percent of the routine done in one ISO week up to `on`, skipped days left out; None if nothing counted."""
    skip = board[0].skip if board else set()
    done = scheduled = 0
    for offset in range(7):
        day = monday + dt.timedelta(days=offset)
        if day > on:
            break
        if day in skip:
            continue
        d, s = routine_day(board, day)
        done, scheduled = done + d, scheduled + s
    return done / scheduled * 100 if scheduled else None


def routine_week_streak(board: list[HabitDays], on: dt.date) -> int:
    """Consecutive ISO weeks with >= ROUTINE_WEEK_PCT % of the routine done; the current week once it is there.
    Weeks with nothing to count (all paused) are stepped over."""
    if not board:
        return 0
    first = week_start(min(d.habit.start_date for d in board))
    week = week_start(on)
    pct = routine_week_pct(board, week, on)
    if pct is None or pct < ROUTINE_WEEK_PCT:
        week -= dt.timedelta(weeks=1)
    streak = 0
    while week >= first:
        pct = routine_week_pct(board, week, on)
        if pct is not None:
            if pct < ROUTINE_WEEK_PCT:
                break
            streak += 1
        week -= dt.timedelta(weeks=1)
    return streak


def resolve_habit(session: Session, title: str) -> tuple[Habit | None, list[tuple[Habit, float]]]:
    """Active habit by title: exact (case- and accent-insensitive) match, else pg_trgm candidates (best first)."""

    def normalized(value):  # SQL expression
        return func.f_unaccent(func.lower(value))

    active = col(Habit.archived_at).is_(None)
    query = title.strip()
    exact = session.exec(select(Habit).where(active, normalized(Habit.title) == normalized(query))).first()
    if exact is not None:
        return exact, [(exact, 1.0)]
    score = func.greatest(
        func.similarity(normalized(Habit.title), normalized(query)),
        func.word_similarity(normalized(query), normalized(Habit.title)),
    )
    rows = session.exec(select(Habit, score).where(active, score >= MIN_SIMILARITY).order_by(score.desc()).limit(3))
    return None, [(habit, round(float(s), 2)) for habit, s in rows]
