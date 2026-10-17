"""Strong app CSV import, tuned to the user's real export (docs/plan-review-2026-10-17.md §G1, SPEC §6.3)."""

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.models.gym import EndedBy, Exercise, MuscleGroup, SetType, Workout, WorkoutSet, WorkoutSource
from app.timeutils import localize

REQUIRED_COLUMNS = {"Date", "Workout Name", "Exercise Name", "Set Order", "Weight", "Reps"}
STRONG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
# Longer than this means the workout was never finished in Strong (62 % of the real export)
FORGOTTEN_FINISH = dt.timedelta(hours=4)
ESTIMATED_MINUTES_PER_SET = 3  # the user's average over properly finished workouts
LBS_TO_KG = 0.45359237
SET_MARKERS = {"W": SetType.warmup, "D": SetType.drop, "F": SetType.failure}


@dataclass(frozen=True)
class RemapRule:
    """The user logged a movement under the closest Strong exercise and marked it with a sticky note."""

    strong_name: str
    map_to: str
    muscle_group: MuscleGroup
    equipment: str | None = None
    marker_note: str | None = None  # dropped from imported sets
    all_workouts: bool = True  # False: only workouts where the marker note appears


DEFAULT_REMAP_RULES = (
    RemapRule(
        "Lat Pulldown (Machine)",
        "Bent-over Pulldown",
        MuscleGroup.back,
        "machine",
        marker_note="Takovej ten bent over pulldown",
    ),
    RemapRule("Lat Pulldown - Underhand (Cable)", "Kelso Shrug", MuscleGroup.back, "cable", marker_note="Kelso shrug"),
)

# Ordered: more specific phrases first ("reverse fly" before "fly", "leg curl" before "curl")
_MUSCLE_KEYWORDS: list[tuple[str, MuscleGroup]] = [
    ("reverse fly", MuscleGroup.shoulders),
    ("rear delt", MuscleGroup.shoulders),
    ("face pull", MuscleGroup.shoulders),
    ("leg raise", MuscleGroup.core),
    ("leg curl", MuscleGroup.legs),
    ("leg extension", MuscleGroup.legs),
    ("leg press", MuscleGroup.legs),
    ("back extension", MuscleGroup.back),
    ("romanian", MuscleGroup.legs),
    ("calf", MuscleGroup.legs),
    ("squat", MuscleGroup.legs),
    ("lunge", MuscleGroup.legs),
    ("hip", MuscleGroup.legs),
    ("glute", MuscleGroup.legs),
    ("deadlift", MuscleGroup.back),
    ("bench", MuscleGroup.chest),
    ("chest", MuscleGroup.chest),
    ("fly", MuscleGroup.chest),
    ("dip", MuscleGroup.chest),
    ("push up", MuscleGroup.chest),
    ("row", MuscleGroup.back),
    ("pulldown", MuscleGroup.back),
    ("pull up", MuscleGroup.back),
    ("chin up", MuscleGroup.back),
    ("shrug", MuscleGroup.back),
    ("lateral", MuscleGroup.shoulders),
    ("shoulder", MuscleGroup.shoulders),
    ("overhead", MuscleGroup.shoulders),
    ("military", MuscleGroup.shoulders),
    ("curl", MuscleGroup.arms),
    ("tricep", MuscleGroup.arms),
    ("bicep", MuscleGroup.arms),
    ("skullcrusher", MuscleGroup.arms),
    ("pushdown", MuscleGroup.arms),
    ("kickback", MuscleGroup.arms),
    ("crunch", MuscleGroup.core),
    ("plank", MuscleGroup.core),
    ("side bend", MuscleGroup.core),
    ("run", MuscleGroup.cardio),
    ("bike", MuscleGroup.cardio),
    ("rowing", MuscleGroup.cardio),
]


class StrongImportError(ValueError):
    pass


@dataclass
class ImportSummary:
    workouts_created: int = 0
    workouts_skipped: int = 0
    sets_created: int = 0
    exercises_created: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def guess_muscle_group(name: str) -> MuscleGroup | None:
    lowered = name.casefold()
    return next((group for keyword, group in _MUSCLE_KEYWORDS if keyword in lowered), None)


def parse_duration(value: str) -> dt.timedelta | None:
    """Strong durations: "1h 8m", "39m", "1h", "2 103h 34m" (NBSP as thousands separator)."""
    compact = re.sub(r"\s", "", value)  # \s also matches NBSP / narrow NBSP in str patterns
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", compact)
    if not compact or match is None:
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return dt.timedelta(hours=hours, minutes=minutes, seconds=seconds)


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return float(value.replace(",", "."))  # decimal comma in some locales


def _positive(value: str | None) -> float | None:
    number = _number(value)
    return number if number else None  # Strong writes 0 for "not used"


def import_strong_csv(
    session: Session,
    content: bytes,
    weight_unit: str = "kg",
    rules: tuple[RemapRule, ...] | list[RemapRule] = DEFAULT_REMAP_RULES,
) -> ImportSummary:
    text = content.decode("utf-8-sig")
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") > header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise StrongImportError(f"Not a Strong export, missing columns: {', '.join(sorted(missing))}")

    workouts: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in reader:
        workouts.setdefault((row["Date"], row["Workout Name"]), []).append(row)

    summary = ImportSummary()
    rules_by_name = {rule.strong_name: rule for rule in rules}
    exercise_ids = {e.name: e.id for e in session.exec(select(Exercise)).all()}
    estimated: list[str] = []
    weight_factor = LBS_TO_KG if weight_unit == "lbs" else 1.0

    for (date_text, name), rows in workouts.items():
        try:
            started_at = localize(dt.datetime.strptime(date_text, STRONG_DATE_FORMAT))  # noqa: DTZ007  (localized)
        except ValueError:
            raise StrongImportError(f"Unrecognised date {date_text!r}") from None
        already = session.exec(
            select(Workout.id).where(
                Workout.source == WorkoutSource.strong_import, Workout.started_at == started_at, Workout.name == name
            )
        ).first()
        if already is not None:
            summary.workouts_skipped += 1
            continue

        duration = parse_duration(rows[0].get("Duration") or "")
        if duration is None or duration > FORGOTTEN_FINISH:
            ended_at = started_at + dt.timedelta(minutes=ESTIMATED_MINUTES_PER_SET * len(rows))
            ended_by = EndedBy.import_estimate
            estimated.append(date_text[:10])
        else:
            ended_at, ended_by = started_at + duration, EndedBy.user
        workout_notes = next((r["Workout Notes"].strip() for r in rows if (r.get("Workout Notes") or "").strip()), None)
        workout = Workout(
            name=name,
            started_at=started_at,
            ended_at=ended_at,
            ended_by=ended_by,
            source=WorkoutSource.strong_import,
            notes=workout_notes,
        )
        session.add(workout)

        rows_by_exercise: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            rows_by_exercise.setdefault(row["Exercise Name"], []).append(row)

        for exercise_order, (strong_name, exercise_rows) in enumerate(rows_by_exercise.items(), start=1):
            rule = rules_by_name.get(strong_name)
            marker = rule.marker_note.casefold() if rule and rule.marker_note else None
            notes = {(r.get("Notes") or "").strip().casefold() for r in exercise_rows}
            marked = marker is not None and marker in notes
            remap = rule is not None and (rule.all_workouts or marked)
            exercise_name = rule.map_to if remap and rule else strong_name
            exercise_id = exercise_ids.get(exercise_name) or _create_exercise(
                session, exercise_name, rule if remap else None, summary
            )
            exercise_ids[exercise_name] = exercise_id

            for counter, row in enumerate(exercise_rows, start=1):
                order_text = (row.get("Set Order") or "").strip()
                set_type = SET_MARKERS.get(order_text.upper(), SetType.normal)
                note = (row.get("Notes") or "").strip() or None
                if note and marker and note.casefold() == marker:
                    note = None
                weight = _number(row.get("Weight"))
                reps = _number(row.get("Reps"))
                seconds = _positive(row.get("Seconds"))
                session.add(
                    WorkoutSet(
                        workout_id=workout.id,
                        exercise_id=exercise_id,
                        exercise_order=exercise_order,
                        set_order=int(order_text) if order_text.isdigit() else counter,
                        set_type=set_type,
                        weight_kg=round(weight * weight_factor, 2) if weight is not None else None,
                        reps=int(reps) if reps is not None else None,
                        duration_s=int(seconds) if seconds else None,
                        distance_m=_positive(row.get("Distance")),
                        rpe=_number(row.get("RPE")),
                        completed=True,
                        notes=note,
                    )
                )
                summary.sets_created += 1
        summary.workouts_created += 1

    if estimated:
        summary.warnings.append(
            f"{len(estimated)} workouts were never finished in Strong (duration missing or over 4 h); "
            f"end times estimated at {ESTIMATED_MINUTES_PER_SET} min per set. First: {', '.join(estimated[:5])}"
        )
    session.commit()
    return summary


def _create_exercise(session: Session, name: str, rule: RemapRule | None, summary: ImportSummary) -> int:
    if rule is not None:
        group, equipment = rule.muscle_group, rule.equipment
    else:
        group, equipment = guess_muscle_group(name), None
        if group is None:
            group = MuscleGroup.full_body
            summary.warnings.append(f"Unknown muscle group for new exercise {name!r}; set to full_body, please fix")
    exercise = Exercise(name=name, muscle_group=group, equipment=equipment)
    session.add(exercise)
    session.flush()
    summary.exercises_created.append(name)
    assert exercise.id is not None
    return exercise.id
