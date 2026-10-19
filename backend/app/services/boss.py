"""RPG layer, step 7.3 (E22): the marathon as the boss. Only the goal race; the half marathon is not a boss (user).

- Max HP = planned km of every plan week up to the race (the plan's upper bound per week).
- Every km run since the plan's first week hits the boss.
- A skipped planned run heals it: a planned day of the day-by-day schedule that passed without a run that day or a
  day either side (a run moved by one day still counts; each run covers one planned day) gives its km back;
  a finished week without a daily schedule heals by its shortfall against the plan's lower bound.
- Defeated only by the race itself: a run of >= DEFEAT_KM on race day; its time is the trophy. A race day that
  passes without one leaves the boss undefeated ("missed").
"""

import datetime as dt
from dataclasses import dataclass, field

from sqlmodel import Session, col, select

from app.models.coach import Race, TrainingDay, TrainingWeek
from app.models.running import Activity
from app.services.run_analysis import RUN_TYPES
from app.timeutils import day_bounds, local_date, today

DEFEAT_KM = 40.0
CZECH_DAYS = ("po", "út", "st", "čt", "pá", "so", "ne")


@dataclass
class BossEvent:
    date: dt.date
    kind: str  # "hit" | "heal"
    km: float
    text: str


@dataclass
class Boss:
    name: str
    race_date: dt.date
    days_left: int
    max_hp: float
    hp: float
    damage_km: float
    heal_km: float
    status: str  # "active" | "defeated" | "missed"
    result_seconds: int | None = None
    result_km: float | None = None
    events: list[BossEvent] = field(default_factory=list)  # newest first


def _km(value: float) -> str:
    return f"{value:.1f}".replace(".", ",").removesuffix(",0")


def _planned_km(low: float | None, high: float | None) -> float:
    return high if high is not None else (low or 0.0)


def marathon_boss(session: Session, on: dt.date | None = None) -> Boss | None:
    on = on or today()
    races = select(Race).where(~col(Race.hidden))
    race = (
        session.exec(races.where(col(Race.is_goal_race)).order_by(col(Race.date).desc()).limit(1)).first()
        or session.exec(races.where(col(Race.distance_km) >= DEFEAT_KM).order_by(col(Race.date))).first()
    )
    if race is None:
        return None
    weeks = session.exec(
        select(TrainingWeek).where(TrainingWeek.week_start <= race.date).order_by(col(TrainingWeek.week_start))
    ).all()
    if not weeks:
        return None
    start = weeks[0].week_start
    max_hp = round(sum(_planned_km(w.km_min, w.km_max) for w in weeks), 1)

    lo, _ = day_bounds(start)
    _, hi = day_bounds(min(on, race.date))
    runs = session.exec(
        select(Activity)
        .where(
            col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= lo, col(Activity.start_time) < hi
        )
        .order_by(col(Activity.start_time))
    ).all()
    run_days: dict[dt.date, float] = {}
    for activity in runs:
        day = local_date(activity.start_time)
        run_days[day] = run_days.get(day, 0.0) + activity.distance_meters / 1000
    plan_days = session.exec(select(TrainingDay).where(col(TrainingDay.planned_date).between(start, race.date))).all()
    scheduled_weeks = {d.planned_date - dt.timedelta(days=d.planned_date.weekday()) for d in plan_days}

    events: list[BossEvent] = []
    for week in weeks:
        if week.week_start > on:
            break
        week_km = sum(km for day, km in run_days.items() if week.week_start <= day <= week.week_end)
        if week_km:
            last = min(on, week.week_end)
            span = f"{week.week_start.day}. {week.week_start.month}.–{last.day}. {last.month}."
            events.append(BossEvent(last, "hit", round(week_km, 1), f"Odběhnuto {_km(week_km)} km ({span})"))
        if week.week_start not in scheduled_weeks and week.week_end < on and week.km_min:
            shortfall = week.km_min - week_km
            if shortfall > 0:
                text = f"Týden {week.week_start.day}. {week.week_start.month}. pod plánem o {_km(shortfall)} km"
                events.append(BossEvent(week.week_end, "heal", round(shortfall, 1), text))
    used: set[dt.date] = set()
    for day in sorted(plan_days, key=lambda d: d.planned_date):
        planned = _planned_km(day.km_min, day.km_max)
        if day.is_rest or not planned or day.planned_date >= on:
            continue
        nearby = [day.planned_date + dt.timedelta(days=o) for o in (0, -1, 1)]
        match = next((d for d in nearby if d in run_days and d not in used), None)
        if match is not None:
            used.add(match)
            continue
        when = day.planned_date
        text = f"Vynechaný běh {CZECH_DAYS[when.weekday()]} {when.day}. {when.month}.: {day.text}"
        events.append(BossEvent(day.planned_date, "heal", planned, text))

    damage = round(sum(e.km for e in events if e.kind == "hit"), 1)
    heal = round(sum(e.km for e in events if e.kind == "heal"), 1)
    boss = Boss(
        name=race.name,
        race_date=race.date,
        days_left=(race.date - on).days,
        max_hp=max_hp,
        hp=round(min(max_hp, max(0.0, max_hp - damage + heal)), 1),
        damage_km=damage,
        heal_km=heal,
        status="active",
        events=sorted(events, key=lambda e: e.date, reverse=True),
    )
    if on >= race.date:
        race_runs = [a for a in runs if local_date(a.start_time) == race.date and a.distance_meters / 1000 >= DEFEAT_KM]
        if race_runs:
            best = max(race_runs, key=lambda a: a.distance_meters)
            boss.status, boss.hp = "defeated", 0.0
            boss.result_seconds, boss.result_km = best.duration_seconds, round(best.distance_meters / 1000, 2)
        elif on > race.date:
            boss.status = "missed"
    return boss
