import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.config import settings
from app.models.bucket import BucketItem, BucketStep, VisitedCountry
from app.models.gym import Exercise, Workout, WorkoutSet
from app.models.habits import Habit
from app.models.rpg import RpgPause
from app.models.running import Activity
from app.services import bucket as bk
from app.services import rpg
from app.services.badges import compute_badges
from app.timeutils import today

ADDED = dt.datetime(2026, 10, 1, 12, tzinfo=dt.UTC)


def d(day: int, month: int = 10, year: int = 2026) -> dt.date:
    return dt.date(year, month, day)


@pytest.fixture
def empty(session: Session) -> Session:
    for model in (BucketStep, BucketItem, VisitedCountry, Habit):
        session.exec(delete(model))
    session.commit()
    return session


def item(session: Session, title: str, rarity: int = 1, **fields) -> BucketItem:
    row = BucketItem(title=title, category=fields.pop("category", "experience"), rarity=rarity, created_at=ADDED)
    for name, value in fields.items():
        setattr(row, name, value)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def entries(ledger: rpg.Ledger, *kinds: str) -> list[tuple[dt.date, int, str]]:
    return [(e.date, e.amount, e.text) for e in ledger.entries if e.kind in kinds]


def run(session: Session, day: dt.date, km: float, kind: str = "Run", elevation: float | None = None) -> None:
    start = dt.datetime.combine(day, dt.time(8), tzinfo=settings.tz)
    session.add(
        Activity(
            start_time=start,
            activity_type=kind,
            distance_meters=km * 1000,
            duration_seconds=3600,
            elevation_gain_m=elevation,
        )
    )
    session.commit()


def test_seed_from_the_migration(session: Session) -> None:
    items = session.exec(select(BucketItem)).all()
    state = bk.load(session, d(20))

    assert len(items) == 132
    assert sum(i.done_before_app for i in items) == 34
    assert not any(s.xp for s in state.items)  # no retroactive XP (B6)
    russian = next(i for i in items if i.title == "Naučit se rusky")
    steps = session.exec(select(BucketStep).where(BucketStep.item_id == russian.id)).all()
    assert [s.title for s in sorted(steps, key=lambda s: s.position)] == ["Azbuka", "A1", "A2", "B1"]
    lsit = next(i for i in items if i.title == "L-sit")
    assert lsit.auto_rule == "exercise" and session.get(Exercise, lsit.auto_exercise_id).name == "L-Sit"
    assert {c.code for c in state.countries} >= {"CZ", "IT", "JP", "RU"}
    assert set(state.continents) == {"europe", "asia"}


def test_completion_pays_by_rarity_with_year_goal_and_skill(empty: Session) -> None:
    item(empty, "Bungee jumping", rarity=3, done_on=d(10), year_goal=2026)
    item(empty, "Humr", rarity=2, done_on=d(11))

    ledger = rpg.build_ledger(empty, d(12))

    assert entries(ledger, "bucket", "bucket_goal") == [
        (d(10), 400, "Bucket list: Bungee jumping (Epická)"),
        (d(10), 200, "Letošní cíl splněn: Bungee jumping"),
        (d(11), 150, "Bucket list: Humr (Vzácná)"),
    ]
    assert ledger.skills["adventure"].xp == 750


def test_no_xp_for_old_completions_or_before_the_app(empty: Session) -> None:
    item(empty, "Ústřice", done_on=d(1, 1, 2020))  # long before it was added
    item(empty, "Sushi", done_before_app=True)
    late_but_ok = item(empty, "Kimči", done_on=d(25, 9))  # within a week before it was added

    state = bk.load(empty, d(12))

    assert [(s.item.title, s.source, s.xp) for s in state.items] == [
        ("Ústřice", "manual", 0),
        ("Sushi", "before", 0),
        ("Kimči", "manual", 50),
    ]
    assert late_but_ok.id


def test_bucket_xp_counts_on_paused_days_and_adventure_never_rusts(empty: Session) -> None:
    item(empty, "Island", rarity=3, done_on=d(5), category="travel", country_codes=["IS"])
    empty.add(RpgPause(start_date=d(3), end_date=d(8)))
    empty.commit()

    ledger = rpg.build_ledger(empty, d(30, 12))

    assert entries(ledger, "bucket") == [(d(5), 400, "Bucket list: Island (Epická)")]
    assert ledger.skills["adventure"].xp == 400
    assert not entries(ledger, "rust")


def test_auto_rules_marathon_exercise_and_hike(empty: Session, exercises: dict[str, int]) -> None:
    lsit_id = empty.exec(select(Exercise.id).where(Exercise.name == "L-Sit")).one()
    marathon = item(empty, "Uběhnout maraton", rarity=4, auto_rule="marathon")
    lsit = item(empty, "L-sit", rarity=2, auto_rule="exercise", auto_exercise_id=lsit_id)
    hike = item(empty, "Vylézt na horu", rarity=2, auto_rule="hike", auto_threshold=1000)
    run(empty, d(4), 41.0)  # not a marathon, no race that day
    run(empty, d(5), 42.3)
    run(empty, d(6), 12, kind="Hike", elevation=850)
    run(empty, d(7), 15, kind="Hike", elevation=1240)
    workout = Workout(id=uuid.uuid4(), name="Skills", started_at=dt.datetime(2026, 10, 8, 18, tzinfo=settings.tz))
    empty.add(workout)
    empty.flush()
    empty.add(WorkoutSet(workout_id=workout.id, exercise_id=lsit_id, exercise_order=1, set_order=1, duration_s=15))
    empty.commit()

    states = {s.item.id: s for s in bk.load(empty, d(12)).items}

    assert (states[marathon.id].done_on, states[marathon.id].auto_label) == (d(5), "Běh 42,3 km")
    assert (states[lsit.id].done_on, states[lsit.id].auto_label) == (d(8), "Gym: L-Sit")
    assert (states[hike.id].done_on, states[hike.id].auto_label) == (d(7), "Túra s převýšením 1 240 m")
    assert states[marathon.id].source == "auto" and states[marathon.id].xp == 1000


def test_marathon_on_race_day_counts_from_40_km(empty: Session) -> None:
    from app.models.coach import Race

    empty.exec(delete(Race))
    empty.add(Race(name="Maraton", date=d(18), distance_km=42.195, is_goal_race=True))
    empty.commit()
    marathon = item(empty, "Uběhnout maraton", rarity=4, auto_rule="marathon")
    run(empty, d(18), 41.6)

    state = next(s for s in bk.load(empty, d(20)).items if s.item.id == marathon.id)

    assert state.done_on == d(18)


def test_countries_continents_and_the_continents_item(empty: Session) -> None:
    seven = item(empty, "Všech 7 kontinentů", rarity=4, auto_rule="continents", auto_threshold=7)
    item(empty, "Japonsko", category="travel", done_before_app=True, country_codes=["JP"])
    empty.add(VisitedCountry(code="CZ"))  # before the app
    for code, day in (("US", d(2)), ("BR", d(3)), ("EG", d(4)), ("AU", d(5))):
        empty.add(VisitedCountry(code=code, visited_on=day))
    empty.commit()

    state = bk.load(empty, d(12))
    open_item = next(s for s in state.items if s.item.id == seven.id)
    assert open_item.auto_progress == "6 / 7 kontinentů" and not open_item.done

    empty.add(VisitedCountry(code="AQ", visited_on=d(9)))
    empty.commit()
    state = bk.load(empty, d(12))
    done = next(s for s in state.items if s.item.id == seven.id)

    assert (done.done_on, done.source, done.xp) == (d(9), "auto", 1000)
    assert state.continents["asia"] is None and state.continents["antarctica"] == d(9)
    japan = next(c for c in state.countries if c.code == "JP")
    assert japan.items == ["Japonsko"] and not japan.on_map


def test_steps_and_year_quest(empty: Session) -> None:
    russian = item(empty, "Naučit se rusky", rarity=4)
    empty.add_all(
        [
            BucketStep(item_id=russian.id, position=0, title="Azbuka", done_on=d(3)),
            BucketStep(item_id=russian.id, position=1, title="A1"),
        ]
    )
    for n in range(5):
        item(empty, f"Věc {n}", done_on=d(10 + n))
    empty.commit()

    ledger = rpg.build_ledger(empty, d(20))

    assert entries(ledger, "bucket_step") == [(d(3), 25, "Krok: Naučit se rusky · Azbuka")]
    assert entries(ledger, "bucket_year") == [(d(14), 500, "Rok dobrodružství 2026: 5 splněných položek bucket listu")]
    assert bk.year_progress(bk.load(empty, d(20)), 2026) == (5, d(14))


def test_badges(empty: Session) -> None:
    for n in range(10):
        item(empty, f"Jídlo {n}", category="food", done_before_app=True)
    item(empty, "Peru", rarity=4, category="travel", done_on=d(5), country_codes=["PE"])

    badges = {b.key: b for b in compute_badges(empty, rpg.build_ledger(empty, d(12)), [], d(12))}

    assert badges["bucket_first"].unlocked_on == d(1)  # done before the app: counted from the day it was added
    assert badges["bucket_10"].unlocked_on == d(1)
    assert badges["bucket_legendary"].unlocked_on == d(5)
    assert badges["gourmet"].progress == "10 / 20"
    assert badges["countries_10"].progress == "1 / 10"


def test_api_crud_complete_steps_and_countries(client: TestClient, empty: Session, exercises: dict[str, int]) -> None:
    created = client.post(
        "/api/bucket",
        json={"title": " Seskok padákem ", "category": "adrenaline", "rarity": 3, "cost": 3, "steps": ["Tandem"]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Seskok padákem" and body["xp"] == 400 and not body["done"]
    item_id = body["id"]

    bad = [
        client.post("/api/bucket", json={"title": "X", "category": "travel", "country_codes": ["XX"]}),
        client.post("/api/bucket", json={"title": "X", "category": "skill", "auto_rule": "exercise"}),
        client.patch(f"/api/bucket/{item_id}", json={"done_on": str(today() + dt.timedelta(days=3))}),
    ]
    assert [r.status_code for r in bad] == [422, 422, 422]

    done = client.patch(
        f"/api/bucket/{item_id}", json={"done_on": str(today()), "memory": "Nad Prostějovem", "rating": 5}
    ).json()
    assert done["done"] and done["source"] == "manual" and done["completed_on"] == str(today())
    assert done["memory"] == "Nad Prostějovem" and done["xp"] == 400
    undone = client.patch(f"/api/bucket/{item_id}", json={"done_on": None}).json()
    assert not undone["done"] and undone["title"] == "Seskok padákem"

    step_id = undone["steps"][0]["id"]
    with_step = client.post(f"/api/bucket/{item_id}/steps", json={"title": "Sólo"}).json()
    assert [s["title"] for s in with_step["steps"]] == ["Tandem", "Sólo"]
    ticked = client.patch(f"/api/bucket/steps/{step_id}", json={"done_on": str(today())}).json()
    assert ticked["steps"][0]["done_on"] == str(today())
    assert len(client.delete(f"/api/bucket/steps/{step_id}").json()["steps"]) == 1

    countries = client.put("/api/bucket/countries/at", json={"visited": True}).json()
    assert [(c["code"], c["visited_on"], c["continent"]) for c in countries] == [("AT", str(today()), "europe")]
    kept = client.put("/api/bucket/countries/AT", json={"visited": True}).json()
    assert kept[0]["visited_on"] == str(today())
    before = client.put("/api/bucket/countries/AT", json={"visited": True, "visited_on": None}).json()
    assert before[0]["visited_on"] is None
    assert client.put("/api/bucket/countries/AT", json={"visited": False}).json() == []
    assert client.put("/api/bucket/countries/ZZ", json={"visited": True}).status_code == 404

    board = client.get("/api/bucket").json()
    assert [i["id"] for i in board["items"]] == [item_id]
    assert board["categories"]["adrenaline"] == "Adrenalin" and len(board["rarities"]) == 4
    assert board["country_continents"]["CZ"] == "europe"

    assert client.delete(f"/api/bucket/{item_id}").status_code == 204
    assert client.get("/api/bucket").json()["items"] == []


def test_resolve_by_title(empty: Session) -> None:
    lobster = item(empty, "Humr")
    item(empty, "Bungee jumping")

    assert bk.resolve(empty, "humr")[0] == lobster
    found, candidates = bk.resolve(empty, "bungee")
    assert found is None and candidates[0][0].title == "Bungee jumping"
