"""Daily kcal target from running (E41): formula, plan vs Strava, modes, fueling and the Monday base proposal."""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.body import DailyMetric, DailySourceMetric
from app.models.coach import TrainingDay
from app.models.nutrition import MealLog, MealLogItem, NutritionProfile
from app.models.running import Activity
from app.services.health_ingest import _merge_steps
from app.services.nutrition.targets import (
    Mode,
    RunKind,
    base_proposal,
    classify,
    day_target,
    handle_proposal,
    mode_for,
)
from app.timeutils import day_bounds

MONDAY = dt.date(2026, 11, 2)  # cut mode


@pytest.fixture
def profile(session: Session) -> NutritionProfile:
    profile = NutritionProfile(id=1, kcal_target=2000, protein_target_g=175, fat_target_g=50)
    session.add(profile)
    session.commit()
    return profile


def weigh(session: Session, day: dt.date, kg: float) -> None:
    session.merge(DailyMetric(date=day, weight_kg=kg))
    session.commit()


def plan(session: Session, day: dt.date, text: str, km: float | None = None, rest: bool = False) -> None:
    session.merge(TrainingDay(planned_date=day, text=text, is_rest=rest, km_min=km, km_max=km))
    session.commit()


def strava_run(session: Session, day: dt.date, km: float, hour: int = 7) -> None:
    start, _ = day_bounds(day)
    session.add(
        Activity(
            start_time=start + dt.timedelta(hours=hour),
            activity_type="Run",
            distance_meters=km * 1000,
            duration_seconds=int(km * 360),
        )
    )
    session.commit()


@pytest.mark.parametrize(
    ("today", "tomorrow", "kcal", "carbs"),
    [
        (None, None, 2000, 213),
        (("Easy 5 km", 5), None, 2300, 288),
        (("Easy 5,56 km", 5.56), None, 2350, 300),
        (("Easy 7 km", 7), None, 2450, 325),
        (("Easy 15 km", 15), None, 2950, 450),
        (("Threshold 10 km", 10), None, 2850, 425),
        (("Long run 10 km", 10), None, 2400, 313),
        (None, ("Long run 10 km", 10), 2400, 313),
        (("Long run 14 km", 14), None, 2600, 363),
        (("Long run 20 km", 20), None, 2850, 425),
    ],
)
def test_formula(session: Session, profile: NutritionProfile, today, tomorrow, kcal: int, carbs: int) -> None:
    weigh(session, MONDAY, 82.5)
    for day, line in ((MONDAY, today), (MONDAY + dt.timedelta(days=1), tomorrow)):
        if line:
            plan(session, day, *line)
    target = day_target(session, MONDAY)
    assert (target.kcal, target.carbs_g, target.protein_g, target.fat_g) == (kcal, carbs, 175, 50)


def test_week(session: Session, profile: NutritionProfile) -> None:
    weigh(session, MONDAY, 82.5)
    lines = [("Volno", None, True), ("Easy 5,56 km", 5.56, False), ("Easy 7 km", 7, False), ("Volno", None, True),
             ("Easy 5 km", 5, False), ("Volno", None, True), ("Long run 10 km", 10, False)]  # fmt: skip
    for offset, (text, km, rest) in enumerate(lines):
        plan(session, MONDAY + dt.timedelta(days=offset), text, km, rest)
    kcal = [day_target(session, MONDAY + dt.timedelta(days=offset)).kcal for offset in range(7)]
    assert kcal == [2000, 2350, 2450, 2000, 2300, 2400, 2400]
    saturday = day_target(session, MONDAY + dt.timedelta(days=5))
    assert saturday.runs_text == "long_run_tomorrow:10.0"
    assert [p.label for p in saturday.parts] == ["½ LR zítra 10 km"]


def test_strava_replaces_planned_km_and_keeps_the_type(session: Session, profile: NutritionProfile) -> None:
    weigh(session, MONDAY, 82.5)
    plan(session, MONDAY, "Easy 7 km + odpoledne lower", 7)
    strava_run(session, MONDAY, 5.56)
    target = day_target(session, MONDAY)
    assert (target.kcal, target.runs_text, target.parts[0].source) == (2350, "easy:5.6", "strava")

    plan(session, MONDAY + dt.timedelta(days=1), "Long run 14 km", 14)
    strava_run(session, MONDAY + dt.timedelta(days=1), 10)
    strava_run(session, MONDAY + dt.timedelta(days=1), 3, hour=18)  # off plan: easy
    tuesday = day_target(session, MONDAY + dt.timedelta(days=1))
    assert tuesday.runs_text == "long_run:10.0;easy:3.0"
    assert tuesday.kcal == 2600  # 2000 + 412.5 + 185.6 = 2598 -> 2600


def test_classify() -> None:
    assert classify("Long run 10 km (= 1,10× 9,1)") == RunKind.long_run
    assert classify("✅ LR 16 km") == RunKind.long_run
    assert classify("T 3× 1,5 km") == RunKind.threshold
    assert classify("Threshold 8 km") == RunKind.threshold
    assert classify("Easy 5 km + 4 strides") == RunKind.strides
    assert classify("kopce 6–8× 45 s") == RunKind.hills
    assert classify("Easy 7 km + odpoledne lower") == RunKind.easy


def test_modes_by_date(session: Session, profile: NutritionProfile) -> None:
    assert [mode_for(dt.date.fromisoformat(d)) for d in (
        "2026-10-20", "2026-10-21", "2026-12-20", "2026-12-21", "2027-01-03", "2027-01-04", "2027-01-27",
        "2027-01-28", "2027-02-14", "2027-02-15", "2027-06-01",
    )] == [Mode.off, Mode.cut, Mode.cut, Mode.maintenance, Mode.maintenance, Mode.cut, Mode.cut, Mode.off,
           Mode.off, Mode.maintenance, Mode.maintenance]  # fmt: skip

    weigh(session, dt.date(2026, 12, 21), 82.5)
    assert day_target(session, dt.date(2026, 12, 21)).kcal == 2500  # maintenance: base + 500
    profile.maintenance_offset_kcal = 300
    session.add(profile)
    session.commit()
    assert day_target(session, dt.date(2026, 12, 21)).kcal == 2300
    off = day_target(session, dt.date(2027, 2, 1))
    assert (off.mode, off.kcal, off.carbs_g) == (Mode.off, None, None)


def test_weight_used(session: Session, profile: NutritionProfile) -> None:
    plan(session, MONDAY, "Easy 7 km", 7)
    assert day_target(session, MONDAY).kcal == 2000  # no weight at all: no run kcal
    weigh(session, MONDAY - dt.timedelta(days=30), 80.0)
    assert day_target(session, MONDAY).weight_used_kg == 80.0  # nothing in the window: the last known
    weigh(session, MONDAY - dt.timedelta(days=6), 83.0)
    weigh(session, MONDAY, 82.0)
    assert day_target(session, MONDAY).weight_used_kg == 82.5  # mean of the 7-day window


def test_fueling_is_logged_but_not_against_the_target(client: TestClient, session: Session, profile) -> None:
    weigh(session, MONDAY, 82.5)
    for meal_type, kcal in (("lunch", 1000), ("fueling", 200)):
        meal = MealLog(id=uuid.uuid4(), logged_date=MONDAY, meal_type=meal_type)
        session.add(meal)
        session.flush()
        session.add(MealLogItem(id=uuid.uuid4(), meal_log_id=meal.id, label=meal_type, kcal=kcal, carbs_g=kcal / 4))
    session.commit()
    summary = client.get("/api/nutrition/summary", params={"date": MONDAY.isoformat()}).json()
    kcal = next(n for n in summary["nutrients"] if n["key"] == "kcal")
    assert (kcal["amount"], kcal["target"], kcal["percent"], summary["fueling_kcal"]) == (1200, 2000, 50.0, 200)
    assert summary["target"]["mode"] == "cut"


def _weights(session: Session, monday: dt.date, now: float, before: float) -> None:
    for offset in range(3):
        weigh(session, monday - dt.timedelta(days=offset), now)
        weigh(session, monday - dt.timedelta(days=14 + offset), before)


def _resting(session: Session, day: dt.date, bpm: float) -> None:
    session.add(DailySourceMetric(date=day, source="manual", metric="resting_hr", value=bpm))
    session.commit()


PROPOSAL_MONDAY = dt.date(2026, 11, 16)


@pytest.mark.parametrize(
    ("base", "now", "before", "new_base"),
    [
        (2000, 80.0, 81.4, 2150),  # -0.7 kg/week: too fast
        (2000, 80.0, 80.8, None),  # -0.4: fine
        (2000, 80.0, 80.2, 1900),  # -0.1: too slow
        (1950, 80.0, 80.0, 1900),  # never below 1900
        (1900, 80.0, 79.0, None),  # already at the minimum
    ],
)
def test_weight_trend_proposal(session: Session, profile, base: float, now: float, before: float, new_base) -> None:
    profile.kcal_target = base
    session.add(profile)
    session.commit()
    _weights(session, PROPOSAL_MONDAY, now, before)
    proposal = base_proposal(session, PROPOSAL_MONDAY + dt.timedelta(days=2))
    assert (proposal.new_base if proposal else None) == new_base


def test_proposal_needs_readings_mode_and_date(session: Session, profile: NutritionProfile) -> None:
    _weights(session, PROPOSAL_MONDAY, 80.0, 81.4)
    session.delete(session.get(DailyMetric, PROPOSAL_MONDAY))
    session.commit()
    assert base_proposal(session, PROPOSAL_MONDAY) is None  # only 2 weigh-ins this week
    _weights(session, dt.date(2026, 11, 2), 80.0, 81.4)
    assert base_proposal(session, dt.date(2026, 11, 2)) is None  # before 2026-11-09
    _weights(session, dt.date(2026, 12, 28), 80.0, 81.4)
    assert base_proposal(session, dt.date(2026, 12, 28)) is None  # maintenance


def test_resting_hr_wins_and_proposal_is_one_tap(client: TestClient, session: Session, profile) -> None:
    _weights(session, PROPOSAL_MONDAY, 80.0, 80.2)  # would be -100
    for offset in range(7, 35, 3):
        _resting(session, PROPOSAL_MONDAY - dt.timedelta(days=offset), 50)
    for offset in range(3):
        _resting(session, PROPOSAL_MONDAY - dt.timedelta(days=offset), 56)
    proposal = base_proposal(session, PROPOSAL_MONDAY)
    assert proposal is not None and proposal.new_base == 2200 and "Klidový tep" in proposal.reason

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("app.routers.nutrition.today", lambda: PROPOSAL_MONDAY + dt.timedelta(days=1))
        targets = client.get("/api/nutrition/targets").json()
        assert targets["proposal"]["new_base"] == 2200
        assert targets["tomorrow"]["date"] == "2026-11-18"
    assert handle_proposal(session, accept=True, day=PROPOSAL_MONDAY) is not None
    assert session.get(NutritionProfile, 1).kcal_target == 2200
    assert base_proposal(session, PROPOSAL_MONDAY) is None  # handled this week


def test_resting_hr_quick_entry(client: TestClient, session: Session) -> None:
    assert client.post("/api/metrics", json={"date": "2026-11-02", "resting_hr": 52}).status_code in (200, 201)
    stored = session.get(DailySourceMetric, (dt.date(2026, 11, 2), "manual", "resting_hr"))
    assert stored is not None and stored.value == 52


def test_placeholder_step_totals_count_as_no_data() -> None:
    steps, method, _ = _merge_steps({}, {("samsung_health", "steps_total"): 1, ("samsung_health", "steps_untimed"): 1})
    assert (steps, method) == (None, None)
    steps, _, _ = _merge_steps({}, {("samsung_health", "steps_total"): 1, ("apple_health", "steps_total"): 4200})
    assert steps == 4200
