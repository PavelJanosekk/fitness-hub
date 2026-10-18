"""Estimated daily energy expenditure (E21): base metabolism + steps + training.

Shown next to intake as information only; nothing is subtracted from anything.
- Base: Mifflin-St Jeor BMR x BASE_FACTOR (digestion and everyday movement other than steps).
- Steps: net walking cost of 0.5 kcal/kg/km over a stride of 0.415 x height. Steps recorded during foot
  activities are left out because the activity already counts them.
- Training: Strava's calories when present, else a MET value (Compendium of Physical Activities) or the
  running cost x weight. Both are gross, so the resting energy of the same time (already in the base) is
  taken off.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.body import DailyMetric, StepBucket
from app.models.gym import Workout, WorkoutSet
from app.models.nutrition import NutritionProfile, Sex
from app.models.running import Activity
from app.schemas.body import EnergyDay, EnergyItem
from app.services.health_ingest import BUCKET, floor_bucket
from app.services.run_analysis import RUN_TYPES
from app.timeutils import day_bounds, local_date, now_utc

BASE_FACTOR = 1.15
WALK_COST = 0.5  # net kcal per kg per km
RUN_COST = 1.0  # gross kcal per kg per km
STRIDE_PER_HEIGHT = 0.415
DEFAULT_STRIDE_M = 0.75
FOOT_TYPES = (*RUN_TYPES, "Walk", "Hike")
RUN_CADENCE = 165  # steps per minute, when a day has no 15-min buckets to measure the run's steps
GYM_TYPES = ("WeightTraining", "Workout", "Crossfit")  # a Strava log of a workout already in the gym log
GYM_MET = 3.5  # resistance training, multiple exercises, rests included
MAX_GYM = dt.timedelta(hours=2, minutes=30)  # Strong imports and forgotten finishes have inflated durations
DEFAULT_MET = 5.0
TYPE_MET = {
    "Walk": 3.5,
    "Hike": 6.0,
    "Swim": 6.0,
    "WeightTraining": GYM_MET,
    "Workout": 4.0,
    "Crossfit": 6.0,
    "Yoga": 2.5,
    "Rowing": 7.0,
    "Elliptical": 5.0,
    "StairStepper": 9.0,
    "AlpineSki": 5.3,
    "NordicSki": 9.0,
    "IceSkate": 7.0,
    "InlineSkate": 7.5,
    "RockClimbing": 7.5,
    "EBikeRide": 4.0,
    "EMountainBikeRide": 4.0,
}
RIDE_TYPES = ("Ride", "VirtualRide", "MountainBikeRide", "GravelRide")
RIDE_MET_BY_SPEED = ((16.0, 4.0), (19.0, 6.8), (22.5, 8.0), (25.7, 10.0))  # (below km/h, MET)
RIDE_MET_FAST = 12.0
RIDE_MET_INDOOR = 7.0


@dataclass
class _Session:
    """A gym workout or an activity, in the shape the estimate needs."""

    item: EnergyItem
    start: dt.datetime
    end: dt.datetime
    gross_kcal: float | None  # None: from MET x weight
    met: float


def bmr(profile: NutritionProfile | None, weight_kg: float, day: dt.date) -> float | None:
    if profile is None or None in (profile.sex, profile.birth_year, profile.height_cm):
        return None
    age = day.year - profile.birth_year
    offset = 5 if profile.sex == Sex.male else -161
    return 10 * weight_kg + 6.25 * profile.height_cm - 5 * age + offset


def _ride_met(activity: Activity) -> float:
    if not activity.distance_meters or not activity.duration_seconds:
        return RIDE_MET_INDOOR
    speed = activity.distance_meters / activity.duration_seconds * 3.6
    return next((met for below, met in RIDE_MET_BY_SPEED if speed < below), RIDE_MET_FAST)


def _activity_session(activity: Activity) -> _Session:
    end = activity.start_time + dt.timedelta(seconds=activity.duration_seconds)
    gross = float(activity.calories) if activity.calories is not None else None
    kind = activity.activity_type
    met = _ride_met(activity) if kind in RIDE_TYPES else TYPE_MET.get(kind, DEFAULT_MET)
    item = EnergyItem(
        source="strava" if activity.source == "strava" else "activity",
        activity_type=activity.activity_type,
        name=activity.notes,
        minutes=round(activity.duration_seconds / 60),
        distance_km=round(activity.distance_meters / 1000, 1) if activity.distance_meters else None,
        method="device" if gross is not None else "estimate",
    )
    return _Session(item=item, start=activity.start_time, end=end, gross_kcal=gross, met=met)


def _gym_session(workout: Workout, now: dt.datetime) -> _Session:
    end = min(workout.ended_at or now, workout.started_at + MAX_GYM)
    end = max(end, workout.started_at)
    item = EnergyItem(
        source="gym",
        activity_type="WeightTraining",
        name=workout.name,
        minutes=round((end - workout.started_at).total_seconds() / 60),
        method="estimate",
    )
    return _Session(item=item, start=workout.started_at, end=end, gross_kcal=None, met=GYM_MET)


def _overlaps(a: _Session, b: _Session) -> bool:
    return a.start < b.end and b.start < a.end


def _sessions(session: Session, lo: dt.datetime, hi: dt.datetime) -> dict[dt.date, list[_Session]]:
    now = now_utc()
    gym = [
        _gym_session(workout, now)
        for workout in session.exec(
            select(Workout)
            .where(col(Workout.started_at) >= lo, col(Workout.started_at) < hi)
            .where(
                select(func.count())
                .where(col(WorkoutSet.workout_id) == Workout.id, col(WorkoutSet.completed))
                .scalar_subquery()
                > 0
            )
        )
    ]
    activities = [
        _activity_session(activity)
        for activity in session.exec(
            select(Activity).where(col(Activity.start_time) >= lo, col(Activity.start_time) < hi)
        )
    ]
    # A gym session also recorded on the watch and synced through Strava is one session; the gym log names it
    activities = [
        a for a in activities if a.item.activity_type not in GYM_TYPES or not any(_overlaps(a, g) for g in gym)
    ]
    by_day: dict[dt.date, list[_Session]] = defaultdict(list)
    for item in sorted(gym + activities, key=lambda s: s.start):
        by_day[local_date(item.start)].append(item)
    return by_day


def _merged_buckets(session: Session, lo: dt.datetime, hi: dt.datetime) -> dict[dt.datetime, float]:
    """Highest source per 15-min bucket, as in the daily step merge (E7)."""
    merged: dict[dt.datetime, float] = {}
    for bucket in session.exec(
        select(StepBucket).where(col(StepBucket.bucket_start) >= lo, col(StepBucket.bucket_start) < hi)
    ):
        merged[bucket.bucket_start] = max(merged.get(bucket.bucket_start, 0.0), bucket.steps)
    return merged


def _steps_during(item: _Session, buckets: dict[dt.datetime, float]) -> float:
    """Steps of the 15-min buckets the session covers, prorated for partly covered ones."""
    total = 0.0
    start = floor_bucket(item.start)
    while start < item.end:
        overlap = min(item.end, start + BUCKET) - max(item.start, start)
        total += buckets.get(start, 0.0) * (overlap / BUCKET)
        start += BUCKET
    return total


def _weights(session: Session) -> list[tuple[dt.date, float]]:
    return list(
        session.exec(
            select(DailyMetric.date, DailyMetric.weight_kg)
            .where(col(DailyMetric.weight_kg).is_not(None))
            .order_by(col(DailyMetric.date))
        ).all()
    )


def _weight_on(weights: list[tuple[dt.date, float]], day: dt.date) -> float | None:
    """The newest weight up to the day, else the oldest one after it (history before the first weigh-in)."""
    before = [w for d, w in weights if d <= day]
    if before:
        return before[-1]
    return weights[0][1] if weights else None


def estimate_days(session: Session, start: dt.date, end: dt.date) -> list[EnergyDay]:
    lo, _ = day_bounds(start)
    _, hi = day_bounds(end)
    profile = session.get(NutritionProfile, 1)
    weights = _weights(session)
    sessions = _sessions(session, lo, hi)
    buckets = _merged_buckets(session, lo, hi)
    bucket_days = {local_date(b) for b in buckets}
    steps_by_day = dict(
        session.exec(
            select(DailyMetric.date, DailyMetric.steps).where(col(DailyMetric.date).between(start, end))
        ).all()
    )
    stride_m = profile.height_cm / 100 * STRIDE_PER_HEIGHT if profile and profile.height_cm else DEFAULT_STRIDE_M

    days = []
    for offset in range((end - start).days + 1):
        day = start + dt.timedelta(days=offset)
        day_sessions = sessions.get(day, [])
        weight = _weight_on(weights, day)
        if weight is None:
            days.append(EnergyDay(date=day, items=[s.item for s in day_sessions], missing=["weight"]))
            continue
        basal = bmr(profile, weight, day)
        resting_per_hour = basal / 24 if basal is not None else weight  # 1 MET without a profile

        exercise = 0.0
        foot_steps = 0.0
        for item in day_sessions:
            hours = (item.end - item.start).total_seconds() / 3600
            if item.gross_kcal is not None:
                gross = item.gross_kcal
            elif item.item.activity_type in RUN_TYPES and item.item.distance_km:
                gross = RUN_COST * weight * item.item.distance_km
            else:
                gross = item.met * weight * hours
            item.item.kcal = round(max(0.0, gross - resting_per_hour * hours))
            exercise += item.item.kcal
            if item.item.activity_type in FOOT_TYPES:
                if day in bucket_days:
                    foot_steps += _steps_during(item, buckets)
                elif item.item.activity_type in RUN_TYPES:
                    foot_steps += RUN_CADENCE * hours * 60
                elif item.item.distance_km:
                    foot_steps += item.item.distance_km * 1000 / stride_m

        missing = []
        steps = steps_by_day.get(day)
        counted_steps = steps_kcal = None
        if steps is None:
            missing.append("steps")
        else:
            counted_steps = round(max(0.0, steps - foot_steps))
            steps_kcal = round(WALK_COST * weight * counted_steps * stride_m / 1000)
        base = None
        if basal is None:
            missing.append("profile")
        else:
            base = round(basal * BASE_FACTOR)
        total = base + (steps_kcal or 0) + round(exercise) if base is not None else None
        days.append(
            EnergyDay(
                date=day,
                weight_kg=weight,
                bmr_kcal=round(basal) if basal is not None else None,
                base_kcal=base,
                steps=steps,
                steps_counted=counted_steps,
                steps_kcal=steps_kcal,
                exercise_kcal=round(exercise),
                total_kcal=total,
                missing=missing,
                items=[s.item for s in day_sessions],
            )
        )
    return days
