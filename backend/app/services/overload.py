"""Progressive overload targets (E35, replacing E33's rules): what to lift in the next session of an exercise.

Deterministic, explainable rules on the exercise's own history, no AI; rationale and thresholds in
docs/overload-spec-review-2026-10-20.md. The working sets form blocks that progress on their own: straight sets are
one block, a top set and its back-off sets are two. From the last comparable session (not marked unusual, lifted at
the planned weights) every block takes one step: comeback after a break, more weight, a drop to look at, the missed
target again, or +1 rep on its priority set. Stalls and declines only warn; easier variants are suggestions for the
current workout and never change the plan.
"""

import datetime as dt
import itertools
import math
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models.gym import Exercise, ProgressionStrategy, SetRole, SetType, Workout, WorkoutSet
from app.schemas.gym import (
    ProgressionTarget,
    TargetBlock,
    TargetReason,
    TargetSet,
    TargetSuggestion,
    TargetWarning,
)
from app.timeutils import local_date, today

COMEBACK_DAYS = 21  # a longer break since the last session starts lighter
LIGHTER = 0.9  # comeback / deload: ~10 % off
MAX_DROP = 0.2  # never more than 20 % off (coarse steps on light weights): fewer reps instead
DROP_REPS = 2  # a set below the range and this many reps under its target is a drop
STALL_SESSIONS = 4  # sessions in a row at one weight without a better total -> "stall"
DECLINE_SESSIONS = 3  # totals falling this many sessions in a row -> "decline" and a deload suggestion
DEFAULT_RIR = 1
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


@dataclass(frozen=True)
class Settings:
    rep_min: int
    rep_max: int
    weight_step: float
    sets_max: int | None = None  # opt-in volume progression; None = sets are never added
    target_rir: int = DEFAULT_RIR
    strategy: str = ProgressionStrategy.straight


def settings_for(exercise: Exercise) -> Settings:
    """The exercise's own settings, the equipment's defaults for the rest."""
    rep_min, rep_max, step = _DEFAULTS.get(exercise.equipment, _FALLBACK)
    rep_min = exercise.rep_min or rep_min
    rep_max = max(exercise.rep_max or rep_max, rep_min)  # a custom minimum above the default maximum widens the range
    return Settings(
        rep_min,
        rep_max,
        exercise.weight_step or step,
        exercise.sets_max,
        DEFAULT_RIR if exercise.target_rir is None else exercise.target_rir,
        exercise.strategy or ProgressionStrategy.straight,
    )


@dataclass(frozen=True)
class PastSet:
    set_type: str
    weight_kg: float | None
    reps: int | None
    planned_weight_kg: float | None = None
    planned_reps: int | None = None
    role: str | None = None


@dataclass(frozen=True)
class PastSession:
    date: dt.date  # local day
    sets: list[PastSet]  # completed sets in order
    unusual: bool = False
    fatigue_from: str | None = None  # an earlier exercise of the same muscle group in that workout


@dataclass
class Block:
    """Working sets that progress together: all straight sets, the top set, or the back-off sets."""

    role: str  # SetRole
    indexes: list[int]  # positions in the session's sets
    weight: float  # as planned (as lifted for sessions without a plan)
    reps: list[int]  # as lifted
    targets: list[int | None]  # planned reps
    as_planned: bool = True  # every set lifted at its planned weight

    @property
    def total(self) -> int:
        return sum(self.reps)


def _load(weight: float | None) -> float:
    return round(weight or 0.0, 2)


def _is_working(s: PastSet) -> bool:
    return s.set_type in WORKING_TYPES and bool(s.reps)


def _most_frequent(weights: list[float]) -> float:
    counts = Counter(weights)
    return max(counts, key=lambda w: (counts[w], w))


def _block(session: PastSession, role: str, indexes: list[int], planned: bool) -> Block:
    sets = [session.sets[i] for i in indexes]
    reps = [s.reps or 0 for s in sets]
    if not planned:
        return Block(role, indexes, _load(sets[0].weight_kg), reps, [None] * len(sets))
    return Block(
        role,
        indexes,
        _load(sets[0].planned_weight_kg),
        reps,
        [s.planned_reps for s in sets],
        all(_load(s.weight_kg) == _load(s.planned_weight_kg) for s in sets),
    )


def blocks_of(session: PastSession, strategy: str) -> tuple[list[Block], bool] | None:
    """The session's working sets as blocks of the strategy, and whether a plan of another strategy was reinterpreted.

    Sets planned since E35 carry their role. Older sets (imports, E33) have none and are read from the weights:
    straight = the sets at the most frequent weight (ties: the heavier); top + back-off = the first working set and the
    rest at their most frequent weight. Other sets stay outside the progression. None without working sets.
    """
    working = [i for i, s in enumerate(session.sets) if _is_working(s)]
    if not working:
        return None
    roles = {session.sets[i].role for i in working} - {None}
    with_role = [i for i in working if session.sets[i].role]  # in a planned session, sets added by hand have no role
    if strategy == ProgressionStrategy.top_backoff:
        if roles and roles <= {SetRole.top, SetRole.backoff} and SetRole.top in roles:
            top = [i for i in with_role if session.sets[i].role == SetRole.top][:1]
            back = [i for i in with_role if session.sets[i].role == SetRole.backoff]
            return [_block(session, SetRole.top, top, True)] + (
                [_block(session, SetRole.backoff, back, True)] if back else []
            ), False
        blocks = [_block(session, SetRole.top, working[:1], False)]
        if rest := working[1:]:
            weight = _most_frequent([_load(session.sets[i].weight_kg) for i in rest])
            back = [i for i in rest if _load(session.sets[i].weight_kg) == weight]
            blocks.append(_block(session, SetRole.backoff, back, False))
        return blocks, bool(roles)
    if roles == {SetRole.straight}:
        return [_block(session, SetRole.straight, with_role, True)], False
    weight = _most_frequent([_load(session.sets[i].weight_kg) for i in working])
    block = [i for i in working if _load(session.sets[i].weight_kg) == weight]
    return [_block(session, SetRole.straight, block, False)], bool(roles)


def _as_lifted(session: PastSession, block: Block) -> Block:
    """A block taken at the weight actually lifted (a manual change the user repeated becomes the plan)."""
    weight = _most_frequent([_load(session.sets[i].weight_kg) for i in block.indexes])
    return Block(block.role, block.indexes, weight, block.reps, [None] * len(block.reps))


def _lifted_weights(session: PastSession, blocks: list[Block]) -> list[tuple[float, ...]]:
    return [tuple(_load(session.sets[i].weight_kg) for i in b.indexes) for b in blocks]


def _down(weight: float, steps: int, step: float) -> float | None:
    """The weight `steps` weight steps lighter, unless that is more than MAX_DROP off."""
    lighter = round(weight - steps * step, 2)
    return lighter if lighter > 0 and lighter >= weight * (1 - MAX_DROP) - 1e-9 else None


def _steps_off(weight: float, step: float) -> int:
    """Whole weight steps nearest to ~10 % of the weight, at least one."""
    return max(1, round(weight * (1 - LIGHTER) / step))


def _ready_for_weight(reps: list[int], lo: int, hi: int) -> bool:
    """The first set at the top of the range, middle sets at least at the bottom, the last at most 1 below it."""
    return reps[0] >= hi and all(r >= lo for r in reps[1:-1]) and (len(reps) == 1 or reps[-1] >= lo - 1)


def _references(block: Block, earlier: list[Block]) -> list[int | None]:
    """What each set was expected to reach: its target, else the same set last time at the same weight."""
    prev = earlier[-1] if earlier and earlier[-1].weight == block.weight else None
    return [
        t if t is not None else (prev.reps[i] if prev and i < len(prev.reps) else None)
        for i, t in enumerate(block.targets)
    ]


def _has_drop(block: Block, earlier: list[Block], lo: int) -> bool:
    refs = _references(block, earlier)
    return any(r < lo and ref is not None and r <= ref - DROP_REPS for r, ref in zip(block.reps, refs, strict=True))


def _totals_at(weight: float, history: list[tuple[dt.date, Block]]) -> list[int]:
    """Block totals of the comparable sessions at this weight up to the last one, oldest first; a break ends the run."""
    totals: list[int] = []
    newer: dt.date | None = None
    for date, block in reversed(history):
        if block.weight != weight or (newer and (newer - date).days > COMEBACK_DAYS):
            break
        totals.append(block.total)
        newer = date
    return totals[::-1]


def _stalled(totals: list[int]) -> int:
    """Sessions in a row, up to the last one, that didn't beat the best total before them."""
    stalled, best = 0, -1
    for total in totals:
        if total > best:
            best, stalled = total, 0
        else:
            stalled += 1
    return stalled


@dataclass
class Step:
    reason: TargetReason
    weight: float
    reps: list[int]  # one per set of the block (one more when `added`)
    priority: int | None = None  # the pushed set, index within the block
    added: bool = False
    big_jump: bool = False
    lighter: tuple[float, list[int]] | None = None  # a lighter option for today after a drop


def _comeback(block: Block, settings: Settings) -> Step:
    """After a break: ~10 % less weight in whole steps; ~10 % fewer reps without a load or with too coarse steps."""
    weight, step = block.weight, settings.weight_step
    lighter = _down(weight, _steps_off(weight, step), step) if weight > 0 else None
    if lighter is not None:
        return Step("comeback", lighter, list(block.reps))
    return Step("comeback", weight, [max(1, math.floor(r * LIGHTER)) for r in block.reps])


def _step(
    block: Block,
    earlier: list[Block],
    settings: Settings,
    working_sets: int,
    known_at: Callable[[float], list[int] | None],
) -> Step:
    """The one progression step of a block; `earlier` = comparable blocks of the same role before it, oldest first."""
    weight, reps, n = block.weight, block.reps, len(block.reps)
    lo, hi, step = settings.rep_min, settings.rep_max, settings.weight_step
    loaded = weight > 0

    def own(at: float) -> list[int] | None:
        """The user's own reps at that weight, one per set of the block."""
        known = known_at(at)
        return [known[min(i, len(known) - 1)] for i in range(n)] if known else None

    if loaded and _ready_for_weight(reps, lo, hi):
        heavier = round(weight + step, 2)
        known = own(heavier)
        if known is None:
            # Epley only for the first set; the others keep this exercise's own drop-off between sets
            first = max(1, math.floor(30 * (weight * (1 + reps[0] / 30) / heavier - 1) + 1e-9))
            estimate = [first] + [max(1, round(first * r / reps[0])) for r in reps[1:]]
        else:
            estimate = known
        return Step("return_up" if known else "weight_up", heavier, estimate, big_jump=estimate[0] < lo)

    refs = _references(block, earlier)
    if any(r < lo and ref is not None and r <= ref - DROP_REPS for r, ref in zip(reps, refs, strict=True)):
        plan = [max(r, ref or r) for r, ref in zip(reps, refs, strict=True)]
        down = _down(weight, 1, step) if loaded else None
        repeated = bool(earlier) and earlier[-1].weight == weight and _has_drop(earlier[-1], earlier[:-1], lo)
        if repeated and down is not None:
            return Step("lower", down, own(down) or plan)
        return Step("check_drop", weight, plan, lighter=(down, own(down) or plan) if down else None)

    if any(t is not None and r < t for r, t in zip(reps, block.targets, strict=True)):
        return Step("hold", weight, [max(r, t or r) for r, t in zip(reps, block.targets, strict=True)])

    if settings.sets_max and working_sets < settings.sets_max and block.role != SetRole.top:
        return Step("add_set", weight, [*reps, min(reps)], priority=n, added=True)

    if not loaded:
        priority: int | None = reps.index(min(reps))  # without a load: the weakest set, no cap
    elif reps[0] < hi:
        priority = 0
    else:  # the first later set under its bound (middle sets: the bottom of the range, the last: 1 below it)
        priority = next((i for i in range(1, n) if reps[i] < (lo if i < n - 1 else lo - 1)), None)
    if priority is None:
        return Step("hold", weight, list(reps))
    pushed = list(reps)
    pushed[priority] += 1
    return Step("plus_rep", weight, pushed, priority=priority)


def next_target(sessions: list[PastSession], settings: Settings, on: dt.date) -> ProgressionTarget | None:
    """The next session's planned sets; None without a session that has working sets (no history, time / distance)."""
    read = [(s, *r) for s in sessions if (r := blocks_of(s, settings.strategy)) is not None]
    if not read:
        return None
    comparable: list[tuple[PastSession, list[Block], bool]] = []
    for k, (session, blocks, reinterpreted) in enumerate(read):
        if session.unusual:
            continue
        if all(b.as_planned for b in blocks):
            comparable.append((session, blocks, reinterpreted))
            continue
        # A manual weight change counts for the plan once the previous session repeated it
        prev_session, prev_blocks, _ = read[k - 1] if k else (None, [], False)
        if (
            prev_session
            and not prev_session.unusual
            and not all(b.as_planned for b in prev_blocks)
            and _lifted_weights(session, blocks) == _lifted_weights(prev_session, prev_blocks)
        ):
            comparable.append((session, [_as_lifted(session, b) for b in blocks], reinterpreted))

    days = (on - sessions[-1].date).days
    comeback = days > COMEBACK_DAYS
    warnings: list[TargetWarning] = []
    last, last_blocks, _ = read[-1]
    if not comparable or comparable[-1][0] is not last:
        # Unusual, or not lifted as planned: the next target repeats that session's plan instead of building on it
        mode, base, base_blocks = "plan", last, last_blocks
        warnings.append("last_not_comparable")
    else:
        base, base_blocks, reinterpreted = comparable[-1]
        mode = "step"
        if len(comparable) < 2 or reinterpreted:  # too little to build on: repeat the last values
            mode = "repeat"
            warnings.append("low_confidence")

    history: dict[str, list[tuple[dt.date, Block]]] = {}
    for session, blocks, _ in comparable:
        if session is not base:
            for b in blocks:
                history.setdefault(b.role, []).append((session.date, b))

    def known_at(role: str) -> Callable[[float], list[int] | None]:
        def reps_at(weight: float) -> list[int] | None:
            same = [b for _, b in history.get(role, []) if b.weight == weight]
            return same[-1].reps if same else None

        return reps_at

    in_block = {i: b.role for b in base_blocks for i in b.indexes}
    has_roles = any(s.role for s in base.sets)
    planned: dict[int, TargetSet] = {
        i: TargetSet(set_type=s.set_type, weight_kg=s.weight_kg, reps=s.reps, role=in_block.get(i))
        for i, s in enumerate(base.sets)
        # sets added by hand to a planned session aren't part of the plan
        if i in in_block or not (has_roles and _is_working(s))
    }
    order = list(planned)  # positions in the base session, an added set goes after its block
    working_sets = sum(1 for i in order if i in in_block)
    steps: list[tuple[Block, Step]] = []
    for block in base_blocks:
        if mode == "plan":
            plan = [t if t is not None else r for r, t in zip(block.reps, block.targets, strict=True)]
            block = Block(block.role, block.indexes, block.weight, plan, block.targets)
        if comeback:
            step = _comeback(block, settings)
        elif mode == "step":
            earlier = [b for _, b in history.get(block.role, [])]
            step = _step(block, earlier, settings, working_sets, known_at(block.role))
        else:
            step = Step("hold" if mode == "plan" else "no_data", block.weight, list(block.reps))
        steps.append((block, step))
        loaded = block.weight > 0
        for k, i in enumerate(block.indexes):
            ts = planned[i]
            new_weight = step.weight if loaded else ts.weight_kg
            ts.changed = _load(new_weight) != _load(base.sets[i].weight_kg) or step.reps[k] != base.sets[i].reps
            ts.weight_kg, ts.reps, ts.priority = new_weight, step.reps[k], step.priority == k
        if step.added:
            last = base.sets[block.indexes[-1]]
            key = max(planned) + 1
            planned[key] = TargetSet(
                set_type=last.set_type,
                weight_kg=step.weight if loaded else last.weight_kg,
                reps=step.reps[-1],
                role=block.role,
                changed=True,
                priority=True,
            )
            order.insert(order.index(block.indexes[-1]) + 1, key)

    if comeback:  # sets outside the blocks (a heavier single, ramp-up sets) come down by the same steps
        first = base_blocks[0]
        steps_off = _steps_off(first.weight, settings.weight_step) if first.weight > 0 else 0
        for i, ts in planned.items():
            if i < len(base.sets) and i not in in_block and _is_working(base.sets[i]) and _load(ts.weight_kg) > 0:
                lighter = _down(_load(ts.weight_kg), steps_off, settings.weight_step) if steps_off else None
                if lighter is not None:
                    ts.weight_kg, ts.changed = lighter, True

    stalled = 0
    suggestion: TargetSuggestion | None = None
    if mode == "step" and not comeback:
        declining = False
        for n, (block, _) in enumerate(steps):
            totals = _totals_at(block.weight, [*history.get(block.role, []), (base.date, block)])
            if n == 0:
                stalled = _stalled(totals)
            if _stalled(totals) >= STALL_SESSIONS and "stall" not in warnings:
                warnings.append("stall")
            if len(totals) >= DECLINE_SESSIONS and all(
                a > b for a, b in itertools.pairwise(totals[-DECLINE_SESSIONS:])
            ):
                declining = True
        if declining:
            warnings.append("decline")
            suggestion = TargetSuggestion(kind="deload", sets=_deload([planned[i] for i in order], settings))
        elif lighter_steps := [(b, s) for b, s in steps if s.lighter]:
            sets = [ts.model_copy() for ts in (planned[i] for i in order)]
            by_key = dict(zip(order, sets, strict=True))
            for block, step in lighter_steps:
                weight, reps = step.lighter  # type: ignore[misc]
                for k, i in enumerate(block.indexes):
                    by_key[i].weight_kg, by_key[i].reps, by_key[i].changed = weight, reps[k], True
            suggestion = TargetSuggestion(kind="lighter", sets=sets)
    if any(s.big_jump for _, s in steps):
        warnings.append("big_jump")

    return ProgressionTarget(
        strategy=settings.strategy,
        sets=[planned[i] for i in order],
        blocks=[TargetBlock(role=b.role, reason=s.reason, weight_kg=s.weight) for b, s in steps],
        warnings=warnings,
        suggestion=suggestion,
        fatigue_from=base.fatigue_from if any(s.reason in ("check_drop", "lower") for _, s in steps) else None,
        stalled_sessions=stalled,
        days_since=days,
        rep_min=settings.rep_min,
        rep_max=settings.rep_max,
        weight_step=settings.weight_step,
        sets_max=settings.sets_max,
        target_rir=settings.target_rir,
    )


def _deload(sets: list[TargetSet], settings: Settings) -> list[TargetSet]:
    """A lighter variant for today: ~10 % less weight where the steps allow it, otherwise one working set less."""
    result: list[TargetSet] = []
    dropped: set[str] = set()
    for ts in reversed(sets):
        copy = ts.model_copy(update={"priority": False})
        if ts.role:
            lighter = (
                _down(_load(ts.weight_kg), _steps_off(_load(ts.weight_kg), settings.weight_step), settings.weight_step)
                if _load(ts.weight_kg) > 0
                else None
            )
            if lighter is not None:
                copy.weight_kg, copy.changed = lighter, True
            elif ts.role not in dropped and sum(1 for s in sets if s.role == ts.role) > 1:
                dropped.add(ts.role)  # the last set of the block goes
                continue
        result.append(copy)
    return result[::-1]


def exercise_target(session: Session, exercise: Exercise, on: dt.date | None = None) -> ProgressionTarget | None:
    """The target for the next session of an exercise from its finished workouts."""
    rows = session.exec(
        select(
            Workout.id,
            Workout.started_at,
            WorkoutSet.exercise_order,
            WorkoutSet.set_type,
            WorkoutSet.weight_kg,
            WorkoutSet.reps,
            WorkoutSet.planned_weight_kg,
            WorkoutSet.planned_reps,
            WorkoutSet.role,
            WorkoutSet.unusual,
        )
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(WorkoutSet.exercise_id == exercise.id, col(WorkoutSet.completed), col(Workout.ended_at).is_not(None))
        .order_by(col(Workout.started_at), col(Workout.id), col(WorkoutSet.exercise_order), col(WorkoutSet.set_order))
    ).all()
    earlier = _earlier_same_group(session, exercise, {r[0]: r[2] for r in reversed(rows)})
    sessions = [
        PastSession(
            local_date(started_at),
            [PastSet(r[3], r[4], r[5], r[6], r[7], r[8]) for r in group],
            unusual=any(r[9] for r in group),
            fatigue_from=earlier.get(workout_id),
        )
        for (workout_id, started_at), group in (
            (key, list(group)) for key, group in itertools.groupby(rows, key=lambda r: (r[0], r[1]))
        )
    ]
    return next_target(sessions, settings_for(exercise), on or today())


def _earlier_same_group(
    session: Session, exercise: Exercise, first_order: dict[uuid.UUID, int]
) -> dict[uuid.UUID, str]:
    """Per workout: the last exercise of the same muscle group done before this one (fatigue hint on a drop)."""
    if not first_order:
        return {}
    rows = session.exec(
        select(WorkoutSet.workout_id, WorkoutSet.exercise_order, Exercise.name)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(
            col(WorkoutSet.workout_id).in_(first_order),
            Exercise.muscle_group == exercise.muscle_group,
            WorkoutSet.exercise_id != exercise.id,
            col(WorkoutSet.completed),
        )
        .order_by(col(WorkoutSet.exercise_order))
    ).all()
    return {workout_id: name for workout_id, order, name in rows if order < first_order[workout_id]}
