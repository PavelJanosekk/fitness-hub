import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.body import DailyMetric, StepBucket
from app.models.gym import Workout, WorkoutSet
from app.models.nutrition import NutritionProfile
from app.models.running import Activity

D = dt.date(2026, 10, 10)
UTC = dt.UTC
# Male, 30 years old on D, 180 cm, 80 kg: BMR = 800 + 1125 - 150 + 5
BMR = 1780
RESTING_PER_HOUR = BMR / 24
STRIDE_KM = 1.8 * 0.415 / 1000


def at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, 10, hour, minute, tzinfo=UTC)


def energy(client: TestClient, start: dt.date = D, end: dt.date = D) -> list[dict]:
    response = client.get("/api/metrics/energy", params={"start_date": start.isoformat(), "end_date": end.isoformat()})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def athlete(session: Session) -> None:
    session.add(NutritionProfile(sex="male", birth_year=1996, height_cm=180))
    session.add(DailyMetric(date=D - dt.timedelta(days=3), weight_kg=80))
    session.commit()


def test_rest_day_is_base_plus_steps(client: TestClient, session: Session, athlete: None) -> None:
    session.add(DailyMetric(date=D, steps=10000))
    session.commit()

    (day,) = energy(client)

    assert day["weight_kg"] == 80  # the newest weight before the day
    assert day["bmr_kcal"] == BMR
    assert day["base_kcal"] == round(BMR * 1.15)
    assert day["steps_kcal"] == round(0.5 * 80 * 10000 * STRIDE_KM)
    assert day["exercise_kcal"] == 0
    assert day["total_kcal"] == day["base_kcal"] + day["steps_kcal"]
    assert day["missing"] == []


def test_run_steps_are_not_counted_twice_and_a_watch_logged_gym_session_is_one_session(
    client: TestClient, session: Session, athlete: None, exercises: dict[str, int]
) -> None:
    session.add(DailyMetric(date=D, steps=10000))
    for source, start, steps in [
        ("samsung_health", at(10), 2500),
        ("samsung_health", at(10, 15), 2500),
        ("samsung_health", at(10, 30), 300),  # starts when the run ends
        ("apple_health", at(10), 2000),  # the phone in the pocket: the higher source wins per bucket
    ]:
        session.add(StepBucket(source=source, bucket_start=start, steps=steps))
    session.add(
        Activity(
            external_id="strava:1", source="strava", start_time=at(10), activity_type="Run",
            distance_meters=5000, duration_seconds=1800, calories=450,
        )
    )
    session.add(
        Activity(
            external_id="strava:2", source="strava", start_time=at(16, 5), activity_type="WeightTraining",
            distance_meters=0, duration_seconds=3000,
        )
    )
    workout = Workout(name="Chest tri", started_at=at(16), ended_at=at(17))
    empty = Workout(name="Discarded", started_at=at(18), ended_at=at(19))
    session.add_all([workout, empty])
    session.flush()
    session.add(
        WorkoutSet(
            workout_id=workout.id, exercise_id=next(iter(exercises.values())), exercise_order=1, set_order=1,
            weight_kg=60, reps=8,
        )
    )
    session.commit()

    (day,) = energy(client)

    run, gym = day["items"]
    assert (run["activity_type"], run["method"], run["kcal"]) == ("Run", "device", round(450 - RESTING_PER_HOUR / 2))
    assert (gym["source"], gym["name"], gym["minutes"]) == ("gym", "Chest tri", 60)
    assert gym["kcal"] == round(3.5 * 80 - RESTING_PER_HOUR)
    assert day["steps"] == 10000
    assert day["steps_counted"] == 5000
    assert day["exercise_kcal"] == run["kcal"] + gym["kcal"]
    assert day["total_kcal"] == round(BMR * 1.15) + round(0.5 * 80 * 5000 * STRIDE_KM) + run["kcal"] + gym["kcal"]


def test_estimates_without_device_calories(client: TestClient, session: Session, athlete: None) -> None:
    session.add_all(
        [
            Activity(
                external_id="strava:3", source="strava", start_time=at(7), activity_type="Run",
                distance_meters=10000, duration_seconds=3600,
            ),
            Activity(  # 15 km/h: leisure riding
                external_id="strava:4", source="strava", start_time=at(12), activity_type="Ride",
                distance_meters=15000, duration_seconds=3600,
            ),
        ]
    )
    session.commit()

    (day,) = energy(client)

    run, ride = day["items"]
    assert run["method"] == "estimate"
    assert run["kcal"] == round(1.0 * 80 * 10 - RESTING_PER_HOUR)
    assert ride["kcal"] == round(4.0 * 80 - RESTING_PER_HOUR)
    assert day["missing"] == ["steps"]  # unknown steps are not zero steps
    assert day["steps_kcal"] is None
    assert day["total_kcal"] == round(BMR * 1.15) + run["kcal"] + ride["kcal"]


def test_missing_profile_or_weight_leaves_the_total_unknown(client: TestClient, session: Session) -> None:
    (day,) = energy(client)
    assert day["missing"] == ["weight"]
    assert day["total_kcal"] is None

    session.add(DailyMetric(date=D + dt.timedelta(days=2), weight_kg=81, steps=4000))
    session.commit()

    before, _, after = energy(client, D, D + dt.timedelta(days=2))
    assert before["weight_kg"] == 81  # before the first weigh-in the first weight is used
    assert before["missing"] == ["steps", "profile"]
    assert after["steps_kcal"] is not None  # stride falls back to 0.75 m without a height
    assert after["total_kcal"] is None


def test_energy_range_is_validated(client: TestClient) -> None:
    reversed_range = {"start_date": "2026-10-10", "end_date": "2026-10-09"}
    assert client.get("/api/metrics/energy", params=reversed_range).status_code == 422
    assert len(client.get("/api/metrics/energy").json()) == 1  # today
