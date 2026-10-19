"""Progressive overload targets (E33): what to lift in the next session of an exercise to keep progressing.

Deterministic rules on the exercise's last finished session, no AI. Exactly one step per session, the first that
applies: lighter after a long break or a stall, one step lighter below the rep range, + weight step at the top of the
range, one more set (up to the max), otherwise +1 rep on the weakest set.
"""

import datetime as dt
import itertools
import math
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session, col, select

from app.models.gym import Exercise, SetType, Workout, WorkoutSet
from app.schemas.gym import ProgressionTarget, TargetSet
from app.timeutils import local_date, today

COMEBACK_DAYS = 21  # a longer gap since the last session starts lighter
STALL_SESSIONS = 3  # sessions in a row at one weight without beating its best -> deload
LIGHTER = 0.9  # comeback / deload: ~10 % off
MAX_DROP = 0.2  # never more than 20 % off (coarse steps on light weights): fewer reps instead
WORKING_TYPES = {SetType.normal, SetType.failure}

# equipment -> (rep_min, rep_max, weight_step), the defaults the user approved (E33)
_DEFAULTS: dict[str | None, tuple[int, int, float]] = {
    "barbell": (6, 10, 2.5),
    "dumbbell": (6, 10, 2.5),
    "bodyweight": (6, 10, 2.5),  # applies to added load; without a load reps grow without a cap
    "machine": (8, 12, 5.0),
    "cable": (8, 12, 5.0),
    "plate_loaded": (8, 12, 5.0),
}
_FALLBACK = (8, 12, 2.5)  # band, unknown equipment
SETS_MAX = 3


@dataclass(frozen=True)
class Settings:
    rep_min: int
    rep_max: int
    weight_step: float
    sets_max: int


def settings_for(exercise: Exercise) -> Settings:
    """The exercise's own settings, the equipment's defaults for the rest."""
    rep_min, rep_max, step = _DEFAULTS.get(exercise.equipment, _FALLBACK)
    rep_min = exercise.rep_min or rep_min
    rep_max = max(exercise.rep_max or rep_max, rep_min)  # a custom minimum above the default maximum widens the range
    return Settings(rep_min, rep_max, exercise.weight_step or step, exercise.sets_max or SETS_MAX)


@dataclass(frozen=True)
class PastSet:
    set_type: str
    weight_kg: float | None
    reps: int | None


@dataclass(frozen=True)
class PastSession:
    date: dt.date  # local day
    sets: list[PastSet]  # completed sets in order


def _load(s: PastSet) -> float:
    return round(s.weight_kg or 0.0, 2)


def _is_working(s: PastSet) -> bool:
    return s.set_type in WORKING_TYPES and bool(s.reps)


def working_weight(sets: list[PastSet]) -> float | None:
    """The most frequent load among the working sets (ties: the heavier one); None without a working set."""
    counts = Counter(_load(s) for s in sets if _is_working(s))
    return max(counts, key=lambda w: (counts[w], w)) if counts else None


def stalled_sessions(sessions: list[PastSession], weight: float) -> int:
    """Sessions in a row, up to the last one, at this working weight that didn't beat its best total reps.

    A break longer than COMEBACK_DAYS starts afresh: bests from before it don't count.
    """
    totals: list[int] = []  # newest first
    newer: dt.date | None = None
    for past in reversed(sessions):
        if working_weight(past.sets) != weight or (newer and (newer - past.date).days > COMEBACK_DAYS):
            break
        totals.append(sum(s.reps or 0 for s in past.sets if _is_working(s) and _load(s) == weight))
        newer = past.date
    stalled, best = 0, -1
    for total in reversed(totals):
        if total > best:
            best, stalled = total, 0
        else:
            stalled += 1
    return stalled


def _down(weight: float, steps: int, step: float) -> float | None:
    """The weight `steps` weight steps lighter, unless that is more than MAX_DROP off."""
    lighter = round(weight - steps * step, 2)
    return lighter if lighter > 0 and lighter >= weight * (1 - MAX_DROP) - 1e-9 else None


def _reps_at(weight: float, reps: int, lighter: float) -> int:
    """Reps at a lighter weight for the same Epley 1RM (never fewer than at the heavier weight)."""
    return max(reps, math.floor(30 * (weight * (1 + reps / 30) / lighter - 1) + 1e-9))


def next_target(sessions: list[PastSession], settings: Settings, on: dt.date) -> ProgressionTarget | None:
    """The last session's sets with one progression step applied; None without a session that has working sets."""
    if not sessions:
        return None
    last = sessions[-1]
    weight = working_weight(last.sets)
    if weight is None:
        return None
    planned = [TargetSet(set_type=s.set_type, weight_kg=s.weight_kg, reps=s.reps) for s in last.sets]
    working = [i for i, s in enumerate(last.sets) if _is_working(s)]
    top = [i for i in working if _load(last.sets[i]) == weight]  # the sets the steps work on
    reps = [last.sets[i].reps or 0 for i in top]
    weakest = reps.index(min(reps))
    days = (on - last.date).days
    stalled = stalled_sessions(sessions, weight) if days <= COMEBACK_DAYS else 0  # a break starts afresh
    step = settings.weight_step
    # ~10 % off in whole weight steps; None without a load or when one step is too coarse for the weight
    steps_off = max(1, round(weight * (1 - LIGHTER) / step))
    lighter = _down(weight, steps_off, step) if weight > 0 else None

    def change(i: int, weight_kg: float | None, new_reps: int) -> None:
        s = planned[i]
        s.changed = s.changed or weight_kg != s.weight_kg or new_reps != s.reps
        s.weight_kg, s.reps = weight_kg, new_reps

    kind: Literal["comeback", "deload", "lighter", "weight", "sets", "reps"]
    target_weight = weight
    # A deload needs a lighter weight: fewer reps at the same weight would only feed the next "no progress"
    if days > COMEBACK_DAYS or (stalled >= STALL_SESSIONS and lighter is not None):
        kind = "comeback" if days > COMEBACK_DAYS else "deload"
        for i in working:
            s = last.sets[i]
            if lighter is None:
                change(i, s.weight_kg, max(1, math.floor((s.reps or 0) * LIGHTER)))
            elif _load(s) > 0:  # heavier top sets and lighter extra sets come down by the same steps
                change(i, _down(_load(s), steps_off, step) or s.weight_kg, s.reps or 0)
        target_weight = lighter or weight
    elif weight > 0 and max(reps) < settings.rep_min and (down := _down(weight, 1, step)) is not None:
        kind = "lighter"
        for i, r in zip(top, reps, strict=True):
            change(i, down, _reps_at(weight, r, down))
        target_weight = down
    elif weight > 0 and min(reps) >= settings.rep_max:
        kind = "weight"
        target_weight = round(weight + step, 2)
        for i in top:
            change(i, target_weight, settings.rep_min)
    elif len(working) < settings.sets_max:
        kind = "sets"
        model = last.sets[top[-1]]
        planned.insert(
            top[-1] + 1, TargetSet(set_type=model.set_type, weight_kg=model.weight_kg, reps=min(reps), changed=True)
        )
    else:
        kind = "reps"
        change(top[weakest], planned[top[weakest]].weight_kg, reps[weakest] + 1)
    return ProgressionTarget(
        kind=kind,
        weight_kg=target_weight,
        sets=planned,
        stalled_sessions=stalled,
        days_since=days,
        rep_min=settings.rep_min,
        rep_max=settings.rep_max,
        weight_step=step,
        sets_max=settings.sets_max,
    )


def exercise_target(session: Session, exercise: Exercise, on: dt.date | None = None) -> ProgressionTarget | None:
    """The target for the next session of an exercise from its finished workouts."""
    rows = session.exec(
        select(Workout.id, Workout.started_at, WorkoutSet.set_type, WorkoutSet.weight_kg, WorkoutSet.reps)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WorkoutSet.exercise_id == exercise.id, col(WorkoutSet.completed), col(Workout.ended_at).is_not(None))
        .order_by(col(Workout.started_at), col(Workout.id), col(WorkoutSet.exercise_order), col(WorkoutSet.set_order))
    ).all()
    sessions = [
        PastSession(local_date(started_at), [PastSet(t, w, r) for _, _, t, w, r in group])
        for (_, started_at), group in itertools.groupby(rows, key=lambda r: (r[0], r[1]))
    ]
    return next_target(sessions, settings_for(exercise), on or today())
