"""Strong import against a synthetic CSV that reproduces the quirks of the user's real export."""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.models.gym import Exercise, Workout, WorkoutSet
from app.services.strong_import import guess_muscle_group, parse_duration

HEADER = "Date,Workout Name,Duration,Exercise Name,Set Order,Weight,Reps,Distance,Seconds,Notes,Workout Notes,RPE"
CSV = "\n".join(
    [
        HEADER,
        # Forgotten finish (23 h), sticky remap note on set 1 only, bodyweight + added-load pull-ups
        '2025-09-30 18:00:00,"Back biceps",23h 23m,"Lat Pulldown - Underhand (Cable)",1,60.0,10.0,0,0.0,"Kelso shrug","",',  # noqa: E501
        '2025-09-30 18:00:00,"Back biceps",23h 23m,"Lat Pulldown - Underhand (Cable)",2,60.0,8.0,0,0.0,,,',
        '2025-09-30 18:00:00,"Back biceps",23h 23m,"Pull Up",1,0.0,10.0,0,0.0,"",,',
        '2025-09-30 18:00:00,"Back biceps",23h 23m,"Pull Up",2,25.0,5.0,0,0.0,,,',
        # Normal duration, an exercise unknown to the seed, a free-text note
        '2026-01-12 17:30:00,"Chest tri",1h 8m,"Bench Press (Barbell)",1,100.0,5.0,0,0.0,"",,',
        '2026-01-12 17:30:00,"Chest tri",1h 8m,"Bench Press (Barbell)",2,100.0,4.0,0,0.0,"",,',
        '2026-01-12 17:30:00,"Chest tri",1h 8m,"Cable Kickback",1,10.0,12.0,0,0.0,"lehce",,',
        # NBSP thousands separator; underhand pulldown without the marker note (rule applies to all workouts)
        '2026-03-29 10:00:00,"Back biceps",2\u00a0103h 34m,"Lat Pulldown - Underhand (Cable)",1,60.0,4.0,0,0.0,,,',
    ]
)


def upload(client: TestClient, csv_text: str = CSV, **form) -> dict:
    files = {"file": ("strong_workouts.csv", csv_text.encode(), "text/csv")}
    response = client.post("/api/workouts/import-strong-csv", files=files, data=form)
    assert response.status_code == 200, response.text
    return response.json()


def sets_of(session: Session, exercise_name: str) -> list[WorkoutSet]:
    return list(
        session.exec(
            select(WorkoutSet)
            .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
            .where(Exercise.name == exercise_name)
            .order_by(col(WorkoutSet.set_order))
        ).all()
    )


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("1h 8m", 68), ("39m", 39), ("1h", 60), ("2\u00a0103h 34m", 126214), ("", None), ("bogus", None)],
)
def test_parse_duration(text: str, minutes: int | None) -> None:
    parsed = parse_duration(text)

    assert (parsed.total_seconds() / 60 if parsed else None) == minutes


def test_guess_muscle_group_prefers_specific_phrases() -> None:
    assert guess_muscle_group("Reverse Fly (Cable)") == "shoulders"
    assert guess_muscle_group("Chest Fly (Band)") == "chest"
    assert guess_muscle_group("Lying Leg Curl (Machine)") == "legs"
    assert guess_muscle_group("Hanging Leg Raise") == "core"
    assert guess_muscle_group("Something Odd") is None


def test_import_summary(client: TestClient, exercises: dict[str, int]) -> None:
    summary = upload(client)

    assert summary["workouts_created"] == 3
    assert summary["sets_created"] == 8
    assert summary["exercises_created"] == ["Cable Kickback"]
    assert any("2 workouts were never finished" in w for w in summary["warnings"])


def test_durations_and_local_timestamps(client: TestClient, session: Session, exercises: dict[str, int]) -> None:
    upload(client)
    by_start = {w.started_at: w for w in session.exec(select(Workout)).all()}

    chest = by_start[dt.datetime(2026, 1, 12, 16, 30, tzinfo=dt.UTC)]  # 17:30 CET
    assert chest.ended_at - chest.started_at == dt.timedelta(minutes=68)
    assert chest.ended_by == "user"

    forgotten = by_start[dt.datetime(2025, 9, 30, 16, 0, tzinfo=dt.UTC)]  # 18:00 CEST
    assert forgotten.ended_at - forgotten.started_at == dt.timedelta(minutes=4 * 3)
    assert forgotten.ended_by == "import_estimate"

    after_dst_switch = by_start[dt.datetime(2026, 3, 29, 8, 0, tzinfo=dt.UTC)]  # 10:00 CEST
    assert after_dst_switch.ended_by == "import_estimate"


def test_remap_rules_apply_to_all_workouts_and_drop_marker_note(
    session: Session, client: TestClient, exercises: dict[str, int]
) -> None:
    upload(client)

    assert sets_of(session, "Lat Pulldown - Underhand (Cable)") == []
    kelso = sets_of(session, "Kelso Shrug")
    assert len(kelso) == 3
    assert all(s.notes is None for s in kelso)


def test_dragon_fly_from_strong_lands_on_dragon_flag(
    session: Session, client: TestClient, exercises: dict[str, int]
) -> None:
    row = "2026-01-05 18:00:00,Core,10m,Dragon Fly 🐉,1,0,8,0,0,,,"
    upload(client, "\n".join([HEADER, row]))

    assert [(s.weight_kg, s.reps) for s in sets_of(session, "Dragon Flag")] == [(0.0, 8)]
    assert session.exec(select(Exercise).where(Exercise.name == "Dragon Fly 🐉")).first() is None


def test_bodyweight_and_added_load(session: Session, client: TestClient, exercises: dict[str, int]) -> None:
    upload(client)

    pull_ups = sets_of(session, "Pull Up")
    assert [(s.weight_kg, s.reps) for s in pull_ups] == [(0.0, 10), (25.0, 5)]
    assert all(s.rpe is None and s.duration_s is None and s.distance_m is None for s in pull_ups)


def test_new_exercise_gets_guessed_group_and_notes_are_kept(
    session: Session, client: TestClient, exercises: dict[str, int]
) -> None:
    upload(client)

    kickback = session.exec(select(Exercise).where(Exercise.name == "Cable Kickback")).one()
    assert kickback.muscle_group == "triceps"
    assert sets_of(session, "Cable Kickback")[0].notes == "lehce"


def test_reimport_skips_existing_workouts(client: TestClient, exercises: dict[str, int]) -> None:
    upload(client)

    again = upload(client)

    assert again["workouts_created"] == 0
    assert again["workouts_skipped"] == 3
    assert again["sets_created"] == 0


def test_custom_exercise_map_replaces_defaults(session: Session, client: TestClient, exercises: dict[str, int]) -> None:
    rules = [{"strong_name": "Pull Up", "map_to": "Chin Up", "muscle_group": "back", "all_workouts": True}]

    upload(client, exercise_map=json.dumps(rules))

    assert len(sets_of(session, "Chin Up")) == 2
    assert len(sets_of(session, "Lat Pulldown - Underhand (Cable)")) == 3  # default rules no longer apply


def test_pounds_are_converted(session: Session, client: TestClient, exercises: dict[str, int]) -> None:
    upload(client, weight_unit="lbs")

    assert sets_of(session, "Bench Press (Barbell)")[0].weight_kg == 45.36


def test_semicolon_delimited_export(session: Session, client: TestClient, exercises: dict[str, int]) -> None:
    csv_text = "\n".join(
        [
            HEADER.replace(",", ";"),
            '2026-02-01 09:00:00;"Legs";55m;"Squat (Barbell)";1;"102,5";5;0;0;"";"";',
        ]
    )

    upload(client, csv_text)

    assert sets_of(session, "Squat (Barbell)")[0].weight_kg == 102.5


def test_non_strong_file_is_rejected(client: TestClient) -> None:
    files = {"file": ("x.csv", b"a,b,c\n1,2,3\n", "text/csv")}

    response = client.post("/api/workouts/import-strong-csv", files=files)

    assert response.status_code == 422
    assert "missing columns" in response.json()["detail"]
