"""Idempotent default data. Runs on every container start after migrations: `python -m app.seed`.

Also seeds the USDA foods once (E3; a ~10 MB download on the first start). A failed download only logs a warning:
the app starts anyway and the next start tries again.

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
    ("Bicep Curl (Cable)", M.biceps, "cable"),
    ("Bicep Curl (Dumbbell)", M.biceps, "dumbbell"),
    ("Cable Crunch", M.core, "cable"),
    ("Chest Dip", M.chest, "bodyweight"),
    ("Chest Fly", M.chest, "machine"),
    ("Chest Fly (Band)", M.chest, "band"),
    ("Chest Fly (Dumbbell)", M.chest, "dumbbell"),
    ("Dragon Flag", M.core, "bodyweight"),
    ("Flat Leg Raise", M.core, "bodyweight"),
    ("Hammer Curl (Dumbbell)", M.biceps, "dumbbell"),
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
    ("Preacher Curl (Machine)", M.biceps, "machine"),
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
    ("Triceps Extension", M.triceps, "cable"),
    ("Triceps Pushdown (Cable - Straight Bar)", M.triceps, "cable"),
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
    ("Skullcrusher (Barbell)", M.triceps, "barbell"),
    ("Standing Calf Raise (Machine)", M.legs, "machine"),
    # --- Widely used staples, about five per muscle group ---
    ("Cable Crossover", M.chest, "cable"),
    ("Chest Press (Machine)", M.chest, "machine"),
    ("Decline Bench Press (Barbell)", M.chest, "barbell"),
    ("Incline Bench Press (Smith Machine)", M.chest, "machine"),
    ("Incline Chest Fly (Dumbbell)", M.chest, "dumbbell"),
    ("Lat Pulldown (Cable)", M.back, "cable"),
    ("Seated Row (Cable)", M.back, "cable"),
    ("Bent Over One Arm Row (Dumbbell)", M.back, "dumbbell"),
    ("Straight Arm Pulldown (Cable)", M.back, "cable"),
    ("Pull Up (Assisted)", M.back, "machine"),
    ("Front Squat (Barbell)", M.legs, "barbell"),
    ("Goblet Squat (Dumbbell)", M.legs, "dumbbell"),
    ("Hack Squat (Machine)", M.legs, "machine"),
    ("Seated Leg Curl (Machine)", M.legs, "machine"),
    ("Hip Adductor (Machine)", M.legs, "machine"),
    ("Shoulder Press (Dumbbell)", M.shoulders, "dumbbell"),
    ("Arnold Press (Dumbbell)", M.shoulders, "dumbbell"),
    ("Front Raise (Dumbbell)", M.shoulders, "dumbbell"),
    ("Reverse Fly (Dumbbell)", M.shoulders, "dumbbell"),
    ("Upright Row (Barbell)", M.shoulders, "barbell"),
    ("Bicep Curl (Barbell)", M.biceps, "barbell"),
    ("Bicep Curl (EZ Bar)", M.biceps, "barbell"),
    ("Incline Curl (Dumbbell)", M.biceps, "dumbbell"),
    ("Concentration Curl (Dumbbell)", M.biceps, "dumbbell"),
    ("Preacher Curl (Dumbbell)", M.biceps, "dumbbell"),
    ("Triceps Pushdown (Cable - Rope)", M.triceps, "cable"),
    ("Overhead Triceps Extension (Dumbbell)", M.triceps, "dumbbell"),
    ("Close Grip Bench Press (Barbell)", M.triceps, "barbell"),
    ("Triceps Dip", M.triceps, "bodyweight"),
    ("Triceps Kickback (Dumbbell)", M.triceps, "dumbbell"),
    ("Ab Wheel", M.core, "bodyweight"),
    ("Crunch", M.core, "bodyweight"),
    ("Russian Twist", M.core, "bodyweight"),
    ("Side Plank", M.core, "bodyweight"),
    ("Pallof Press (Cable)", M.core, "cable"),
    # --- Calisthenics skills from the bucket list (E36): logging a set completes the item ---
    ("Muscle Up", M.back, "bodyweight"),
    ("L-Sit", M.core, "bodyweight"),
    ("Handstand", M.shoulders, "bodyweight"),
    ("Planche", M.shoulders, "bodyweight"),
]


def seed_exercises(session: Session) -> int:
    """Insert missing default exercises; existing rows (incl. user edits) are left untouched."""
    rows = [{"name": name, "muscle_group": group.value, "equipment": equipment} for name, group, equipment in EXERCISES]
    statement = insert(Exercise).values(rows).on_conflict_do_nothing(index_elements=["name"]).returning(Exercise.id)
    inserted = len(session.connection().execute(statement).all())
    session.commit()
    return inserted


if __name__ == "__main__":
    import httpx

    from app.database import engine
    from app.services.nutrition import usda_cs
    from app.services.nutrition.usda import is_seeded, seed_usda

    with Session(engine) as session:
        print(f"seed: {seed_exercises(session)} new exercises")
        if not is_seeded(session):
            try:
                with httpx.Client(timeout=60, headers={"User-Agent": "fitness-hub"}) as http:
                    r = seed_usda(session, http)
                print(f"seed: {r.foods} USDA foods, {r.portions} portions ({r.skipped} skipped: no required macro)")
            except Exception as exc:  # foods are optional at startup; the app must come up anyway
                session.rollback()
                print(f"seed: WARNING USDA foods not seeded, retried on next start: {exc}")
        named, hidden = usda_cs.apply(session)
        if named or hidden:
            print(f"seed: USDA Czech names {named}, hidden {hidden} (E28)")
