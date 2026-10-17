"""Idempotent default data. Runs on every container start after migrations: `python -m app.seed`.

Exercise names follow the Strong app convention, so Strong imports match them. The first block
covers every exercise in the user's real Strong export.
"""

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.models.gym import Exercise, MuscleGroup

M = MuscleGroup

# (name, muscle_group, equipment)
EXERCISES: list[tuple[str, MuscleGroup, str | None]] = [
    # --- From the user's Strong export ---
    ("Back Extension", M.back, "bodyweight"),
    ("Bench Press (Barbell)", M.chest, "barbell"),
    ("Bench Press (Dumbbell)", M.chest, "dumbbell"),
    ("Bicep Curl (Cable)", M.arms, "cable"),
    ("Bicep Curl (Dumbbell)", M.arms, "dumbbell"),
    ("Cable Crunch", M.core, "cable"),
    ("Chest Dip", M.chest, "bodyweight"),
    ("Chest Fly", M.chest, "machine"),
    ("Chest Fly (Band)", M.chest, "band"),
    ("Chest Fly (Dumbbell)", M.chest, "dumbbell"),
    ("Dragon Fly 🐉", M.core, "bodyweight"),
    ("Flat Leg Raise", M.core, "bodyweight"),
    ("Hammer Curl (Dumbbell)", M.arms, "dumbbell"),
    ("Hanging Leg Raise", M.core, "bodyweight"),
    ("Hip Abductor (Machine)", M.legs, "machine"),
    ("Incline Bench Press (Dumbbell)", M.chest, "dumbbell"),
    ("Lat Pulldown (Machine)", M.back, "machine"),
    ("Lat Pulldown - Underhand (Cable)", M.back, "cable"),
    ("Lateral Raise (Cable)", M.shoulders, "cable"),
    ("Lateral Raise (Dumbbell)", M.shoulders, "dumbbell"),
    ("Lateral Raise (Machine)", M.shoulders, "machine"),
    ("Leg Extension (Machine)", M.legs, "machine"),
    ("Leg Press", M.legs, "machine"),
    ("Lying Leg Curl (Machine)", M.legs, "machine"),
    ("Overhead Press (Cable)", M.shoulders, "cable"),
    ("Pendlay Row (Barbell)", M.back, "barbell"),
    ("Preacher Curl (Machine)", M.arms, "machine"),
    ("Pull Up", M.back, "bodyweight"),
    ("Reverse Fly (Cable)", M.shoulders, "cable"),
    ("Reverse Fly (Machine)", M.shoulders, "machine"),
    ("Romanian Deadlift (Barbell)", M.legs, "barbell"),
    ("Seated Calf Raise (Plate Loaded)", M.legs, "plate_loaded"),
    ("Seated Row (Machine)", M.back, "machine"),
    ("Shoulder Press (Machine)", M.shoulders, "machine"),
    ("Shoulder Press (Plate Loaded)", M.shoulders, "plate_loaded"),
    ("Side Bend (Band)", M.core, "band"),
    ("Side Bend (Dumbbell)", M.core, "dumbbell"),
    ("Squat (Barbell)", M.legs, "barbell"),
    ("Strict Military Press (Barbell)", M.shoulders, "barbell"),
    ("T Bar Row", M.back, "plate_loaded"),
    ("Triceps Extension", M.arms, "cable"),
    ("Triceps Pushdown (Cable - Straight Bar)", M.arms, "cable"),
    # --- Real movements the user logged under the closest Strong exercise (Strong import remap rules) ---
    ("Bent-over Pulldown", M.back, "machine"),
    ("Kelso Shrug", M.back, "cable"),
    # --- Common extras ---
    ("Bent Over Row (Barbell)", M.back, "barbell"),
    ("Bulgarian Split Squat (Dumbbell)", M.legs, "dumbbell"),
    ("Chin Up", M.back, "bodyweight"),
    ("Deadlift (Barbell)", M.back, "barbell"),
    ("Face Pull (Cable)", M.shoulders, "cable"),
    ("Hip Thrust (Barbell)", M.legs, "barbell"),
    ("Incline Bench Press (Barbell)", M.chest, "barbell"),
    ("Lunge (Dumbbell)", M.legs, "dumbbell"),
    ("Overhead Press (Barbell)", M.shoulders, "barbell"),
    ("Plank", M.core, "bodyweight"),
    ("Push Up", M.chest, "bodyweight"),
    ("Shrug (Dumbbell)", M.back, "dumbbell"),
    ("Skullcrusher (Barbell)", M.arms, "barbell"),
    ("Standing Calf Raise (Machine)", M.legs, "machine"),
]


def seed_exercises(session: Session) -> int:
    """Insert missing default exercises; existing rows (incl. user edits) are left untouched."""
    rows = [{"name": name, "muscle_group": group.value, "equipment": equipment} for name, group, equipment in EXERCISES]
    statement = insert(Exercise).values(rows).on_conflict_do_nothing(index_elements=["name"]).returning(Exercise.id)
    inserted = len(session.connection().execute(statement).all())
    session.commit()
    return inserted


if __name__ == "__main__":
    from app.database import engine

    with Session(engine) as session:
        print(f"seed: {seed_exercises(session)} new exercises")
