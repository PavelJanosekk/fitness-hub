import datetime as dt
from statistics import fmean

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.body import DailyMetric, DailyMetricKind, DailySourceMetric, HealthSource
from app.models.gym import Exercise, Workout, WorkoutSet
from app.models.nutrition import MealLog, MealLogItem
from app.models.running import Activity
from app.schemas.body import MetricDay, MetricUpsert, WeekStats
from app.services.health_ingest import recompute_day
from app.services.run_analysis import RUN_TYPES
from app.timeutils import day_bounds, local_date, today

ROLLING_DAYS = 7


def upsert_daily_metric(session: Session, body: MetricUpsert) -> DailyMetric:
    """Partial upsert; only non-null fields overwrite. Manual steps/sleep win over device data."""
    day = body.date or today()
    metric = session.get(DailyMetric, day) or DailyMetric(date=day)
    for field, value in body.model_dump(exclude={"date", "steps", "sleep_hours"}).items():
        if value is not None:
            setattr(metric, field, value)
    session.add(metric)
    manual = {DailyMetricKind.steps_total: body.steps, DailyMetricKind.sleep_minutes: body.sleep_hours}
    for kind, value in manual.items():
        if value is not None:
            stored = value * 60 if kind == DailyMetricKind.sleep_minutes else value
            session.merge(DailySourceMetric(date=day, source=HealthSource.manual, metric=kind, value=stored))
    session.flush()
    recompute_day(session, day)
    session.commit()
    session.refresh(metric)
    return metric


def weekly_stats(session: Session, weeks: int) -> list[WeekStats]:
    """Monday-Sunday weeks (oldest first): running km and working sets per muscle group."""
    current = today()
    first_monday = current - dt.timedelta(days=current.weekday(), weeks=weeks - 1)
    lo, _ = day_bounds(first_monday)
    stats = {
        first_monday + dt.timedelta(weeks=i): WeekStats(
            week_start=first_monday + dt.timedelta(weeks=i), run_km=0, runs=0, gym_workouts=0, gym_sets={}
        )
        for i in range(weeks)
    }

    def week_of(moment: dt.datetime) -> WeekStats | None:
        day = local_date(moment)
        return stats.get(day - dt.timedelta(days=day.weekday()))

    for run in session.exec(
        select(Activity).where(col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= lo)
    ):
        if week := week_of(run.start_time):
            week.run_km = round(week.run_km + run.distance_meters / 1000, 1)
            week.runs += 1
    workouts_seen: set = set()
    for workout_id, started_at, group in session.exec(
        select(Workout.id, Workout.started_at, Exercise.muscle_group)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(col(Workout.started_at) >= lo, col(WorkoutSet.completed), WorkoutSet.set_type != "warmup")
    ):
        if week := week_of(started_at):
            week.gym_sets[group] = week.gym_sets.get(group, 0) + 1
            if workout_id not in workouts_seen:
                workouts_seen.add(workout_id)
                week.gym_workouts += 1
    return list(stats.values())


def intake_by_day(session: Session, start: dt.date, end: dt.date) -> dict[dt.date, tuple[float, ...]]:
    """(kcal, protein, carbs, fat) per day that has meal logs. Days without logs are absent, not zero."""
    rows = session.exec(
        select(
            MealLog.logged_date,
            func.sum(MealLogItem.kcal),
            func.sum(MealLogItem.protein_g),
            func.sum(MealLogItem.carbs_g),
            func.sum(MealLogItem.fat_g),
        )
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .where(col(MealLog.logged_date).between(start, end))
        .group_by(col(MealLog.logged_date))
    ).all()
    return {day: (kcal, protein, carbs, fat) for day, kcal, protein, carbs, fat in rows}


def daily_series(session: Session, start: dt.date, end: dt.date) -> list[MetricDay]:
    """One entry per day in [start, end] with 7-day rolling averages over the days that have data."""
    window_start = start - dt.timedelta(days=ROLLING_DAYS - 1)
    metrics = {
        m.date: m for m in session.exec(select(DailyMetric).where(col(DailyMetric.date).between(window_start, end)))
    }
    intake = intake_by_day(session, window_start, end)

    def rolling(day: dt.date, value_of) -> float | None:
        values = [v for offset in range(ROLLING_DAYS) if (v := value_of(day - dt.timedelta(days=offset))) is not None]
        return round(fmean(values), 2) if values else None

    def weight(day: dt.date) -> float | None:
        return metrics[day].weight_kg if day in metrics else None

    def kcal(day: dt.date) -> float | None:
        return intake[day][0] if day in intake else None

    series = []
    for offset in range((end - start).days + 1):
        day = start + dt.timedelta(days=offset)
        metric = metrics.get(day)
        kcal_in, protein, carbs, fat = intake.get(day, (None, None, None, None))
        series.append(
            MetricDay(
                date=day,
                weight_kg=weight(day),
                weight_7d_avg=rolling(day, weight),
                calories_in=kcal_in,
                calories_in_7d_avg=rolling(day, kcal),
                protein_g=protein,
                carbs_g=carbs,
                fat_g=fat,
                calories_out=metric.calories_out if metric else None,
                steps=metric.steps if metric else None,
                sleep_hours=metric.sleep_hours if metric else None,
                notes=metric.notes if metric else None,
            )
        )
    return series
