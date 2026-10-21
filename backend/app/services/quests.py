"""RPG layer, step 7.4 (E22): weekly quests generated from real data, and badges.

Quests are derived, never stored: each ISO week from the routine's first week gets its quests from what was known
before it started (the plan week, the previous 4 weeks of gym / habits), so they don't change during the week.
- run: the week's planned km (lower bound) from the RunningCoach plan
- gym: workouts per week = the average of the previous 4 weeks, 2-4
- muscle: 6 working sets for the muscle group with the fewest sets in the previous 4 weeks
- home: every weekly "Domov" habit of the week
- habit: 5 days of the weakest daily routine habit of the previous 4 weeks
- ability (E37, weeks from ABILITY_QUEST_FROM so earlier weeks keep their quests): one new dovednost, when Mysl got
  the least skill XP of the previous 4 weeks and a note / review habit exists to log it
- side (E45, weeks from SIDE_QUEST_FROM): complete one side quest of any duration, once the list has any
Each completed quest pays XP on the day it is completed; all of them pay a bonus. A finished week's open quests are
recorded as failed (no reward). Values are (tune).
"""

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models.coach import TrainingWeek
from app.models.gym import Exercise, Workout, WorkoutSet
from app.models.habits import HabitFrequency
from app.models.running import Activity
from app.services import abilities as ab
from app.services import habits as hs
from app.services import side_quests as sq
from app.services.run_analysis import RUN_TYPES
from app.services.workouts import WORKING_SET
from app.timeutils import day_bounds, local_date

QUEST_XP = {"run": 150, "gym": 100, "muscle": 80, "home": 80, "habit": 60, "ability": 60, "side": 80}
ABILITY_QUEST_FROM = dt.date(2026, 10, 26)
SIDE_QUEST_FROM = dt.date(2026, 10, 26)
TRAINED_SKILLS = ("strength", "endurance", "nutrition", "discipline", "mind", "home")  # not the rare Dobrodružství
ALL_QUESTS_XP = 100
MUSCLE_SETS = 6
HABIT_DAYS = 5
LOOKBACK_DAYS = 28
GROUPS = {
    "chest": "Hrudník",
    "back": "Záda",
    "legs": "Nohy",
    "shoulders": "Ramena",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "core": "Core",
}


@dataclass
class History:
    """Day-level facts the quests and badges are judged on, loaded once."""

    run_km: dict[dt.date, float] = field(default_factory=lambda: defaultdict(float))
    runs: list[tuple[dt.date, float]] = field(default_factory=list)
    gym_days: Counter[dt.date] = field(default_factory=Counter)  # workouts with working sets per day
    group_sets: dict[dt.date, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    plan_km: dict[dt.date, float] = field(default_factory=dict)  # week start -> planned km (lower bound)
    new_abilities: Counter[dt.date] = field(default_factory=Counter)  # first entries of dovednosti per day
    side_quests: Counter[dt.date] = field(default_factory=Counter)  # paying side quests completed per day
    side_quests_since: dt.date | None = None  # the day the first side quest was added


def load_history(session: Session, start: dt.date, end: dt.date) -> History:
    history = History()
    lo, _ = day_bounds(start)
    _, hi = day_bounds(end)
    for activity in session.exec(
        select(Activity).where(
            col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= lo, col(Activity.start_time) < hi
        )
    ):
        day = local_date(activity.start_time)
        history.run_km[day] += activity.distance_meters / 1000
        history.runs.append((day, activity.distance_meters / 1000))
    seen: set = set()
    for workout_id, started_at, group in session.exec(
        select(Workout.id, Workout.started_at, Exercise.muscle_group)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(WORKING_SET, col(Workout.started_at) >= lo, col(Workout.started_at) < hi)
    ):
        day = local_date(started_at)
        history.group_sets[day][group] += 1
        if workout_id not in seen:
            seen.add(workout_id)
            history.gym_days[day] += 1
    for day, _ in ab.first_days(session, end).values():
        history.new_abilities[day] += 1
    side = sq.load(session, end)
    history.side_quests.update(sq.paying_days(side))
    history.side_quests_since = min((local_date(s.quest.created_at) for s in side), default=None)
    for week in session.exec(select(TrainingWeek)):
        if week.km_min:
            history.plan_km[week.week_start] = week.km_min
    return history


@dataclass
class Quest:
    key: str
    title: str
    target: float
    unit: str
    xp: int
    skill: str | None  # RPG skill the XP goes to; None = by the habit's area (`habit_skill`)
    habit_skill: str | None = None
    progress: float = 0.0
    done_on: dt.date | None = None  # the day the target was reached


def _days(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def week_quests(
    history: History,
    board: list[hs.HabitDays],
    monday: dt.date,
    on: dt.date,
    skill_xp_before: dict[str, int] | None = None,
) -> list[Quest]:
    """The quests of the ISO week starting `monday`, with progress up to `on`; `skill_xp_before` = XP per skill
    in the 4 weeks before it."""
    before = _days(monday - dt.timedelta(days=LOOKBACK_DAYS), monday - dt.timedelta(days=1))
    quests: list[Quest] = []

    if km := history.plan_km.get(monday):
        quests.append(Quest("run", f"Uběhni {km:g} km podle plánu", km, "km", QUEST_XP["run"], "endurance"))

    gym_before = sum(history.gym_days[d] for d in before)
    target = max(2, min(4, round(gym_before / (LOOKBACK_DAYS / 7))))
    quests.append(Quest("gym", f"{target}× posilovna", target, "×", QUEST_XP["gym"], "strength"))

    sets_before: Counter[str] = Counter()
    for d in before:
        sets_before.update(history.group_sets.get(d, Counter()))
    if gym_before:
        weakest = min(GROUPS, key=lambda g: sets_before[g])  # ties: the first in GROUPS order
        quests.append(
            Quest(
                f"muscle:{weakest}",
                f"{MUSCLE_SETS} pracovních sérií: {GROUPS[weakest]}",
                MUSCLE_SETS,
                "sérií",
                QUEST_XP["muscle"],
                "strength",
            )
        )

    home = [
        d
        for d in board
        if d.habit.frequency == HabitFrequency.weekly
        and d.habit.skill == "home"
        and hs.is_active(d.habit, monday + dt.timedelta(days=6))
    ]
    if home:
        quests.append(Quest("home", "Ukliď celý byt", len(home), "úkolů", QUEST_XP["home"], "home"))

    routine = [
        d
        for d in board
        if d.habit.frequency == HabitFrequency.daily and not d.habit.is_bonus and hs.is_active(d.habit, monday)
    ]
    rated = []
    for item in routine:
        done, scheduled = hs.completion(item, before[0], before[-1])
        if scheduled >= 7:
            rated.append((done / scheduled, item.habit.position, item))
    habit_item = min(rated, key=lambda r: (r[0], r[1]))[2] if rated else None
    if habit_item:
        title = f"{habit_item.habit.title}: {HABIT_DAYS}× tento týden"
        quests.append(
            Quest(
                f"habit:{habit_item.habit.id}", title, HABIT_DAYS, "×", QUEST_XP["habit"], None, habit_item.habit.skill
            )
        )

    sunday = monday + dt.timedelta(days=6)
    journal = any(d.habit.log_mode != "check" and hs.is_active(d.habit, sunday) for d in board)
    if monday >= ABILITY_QUEST_FROM and skill_xp_before is not None and journal:
        weakest = min(TRAINED_SKILLS, key=lambda s: (skill_xp_before.get(s, 0), s != "mind"))
        if weakest == "mind":
            quests.append(Quest("ability", "Vyzkoušej novou dovednost", 1, "×", QUEST_XP["ability"], "mind"))

    since = history.side_quests_since
    if monday >= SIDE_QUEST_FROM and since is not None and since <= sunday:
        quests.append(Quest("side", "Dokonči side quest", 1, "×", QUEST_XP["side"], "adventure"))

    # Progress day by day, so the completion day is known
    for day in _days(monday, min(on, monday + dt.timedelta(days=6))):
        for quest in quests:
            if quest.key == "run":
                quest.progress += history.run_km.get(day, 0.0)
            elif quest.key == "gym":
                quest.progress += history.gym_days[day]
            elif quest.key.startswith("muscle:"):
                quest.progress += history.group_sets.get(day, Counter())[quest.key.split(":", 1)[1]]
            elif quest.key == "home":
                quest.progress = sum(
                    1 for d in home if hs.week_count({x for x in d.done if x <= day}, monday) >= d.habit.weekly_target
                )
            elif quest.key.startswith("habit:") and habit_item and day in habit_item.done:
                quest.progress += 1
            elif quest.key == "ability":
                quest.progress += history.new_abilities[day]
            elif quest.key == "side":
                quest.progress += history.side_quests[day]
            if quest.done_on is None and quest.progress >= quest.target - 1e-9:
                quest.done_on = day
    for quest in quests:
        quest.progress = round(quest.progress, 1)
    return quests
