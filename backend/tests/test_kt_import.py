"""KalorickéTabulky import (Phase 5.5). Diaries mirror the shape of a real day (O3, 2026-10-17) with made-up
foods and values; the client is a fake, no network."""

import asyncio
import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from kaloricketabulky.sdk import AuthError, Diary, Snapshot
from sqlmodel import Session, select

from app.config import settings
from app.models.body import DailyMetric
from app.models.nutrition import Food, KTImportState, MealLog, MealLogItem
from app.routers import nutrition as nutrition_router
from app.services.nutrition import kt_import
from app.services.nutrition.kt_import import import_day, import_weights, parse_grams, prepare, run_import

D = dt.date(2026, 10, 10)


def entry(entry_id: str, title: str, unit: str, guid: str | None = "g-egg", **values) -> dict:
    nutrients = {"energy": "54,4", "energyUnit": "kcal", "protein": 4.46, "carbohydrate": 0.34, "fat": 3.91} | values
    return {"id": entry_id, "type": "foodstuff", "guidType": guid, "title": title, "unit": unit, **nutrients}


def diary(*meals: tuple[str, list[dict]]) -> Diary:
    times = [{"id": f"m{i}", "title": title, "foodstuff": items} for i, (title, items) in enumerate(meals)]
    return Diary.model_validate({"energyUnit": "kcal", "energyTotal": 0, "times": times})


DAY = diary(
    (
        "Snídaně",
        [
            entry("e1", "vejce slepičí", "36 x 1 g", sodium=0.05, calcium=0.0194),
            entry("e2", "tekuté bílky", "200 x 1 g", guid="g-whites", energy="100", protein=20.0, carbohydrate=2.4,
                  fat=1.0, sugar=2.4, salt=0.8),
        ],
    ),
    ("Oběd", [entry("e3", "topinka na tuku", "2,5 x kus (50 g)", guid="g-toast", energy="526", protein=6.25,
                    carbohydrate=50.0, fat=31.0)]),
    ("Druhá večeře", [entry("e4", "mandlové mléko", "200 x 1 ml", guid="g-milk", energy="111,7", energyUnit="kJ",
                            protein=0.0, carbohydrate=0.2, fat=2.2)]),
)  # fmt: skip


@pytest.mark.parametrize(
    ("unit", "grams"),
    [
        ("200 x 1 g", 200),
        ("449 g", 449),
        ("2,5 x kus (50 g)", 125),
        ("0,6 x porce (50 g)", 30),
        ("200 x 1 ml", 200),
        ("1 000 g", 1000),
        ("1 kus", None),
        ("", None),
        (None, None),
        ("0 g", None),
    ],
)
def test_parse_grams(unit: str | None, grams: float | None) -> None:
    assert parse_grams(unit) == grams


def foods(session: Session) -> dict[str, Food]:
    return {f.external_id: f for f in session.exec(select(Food))}  # type: ignore[misc]


def test_a_day_becomes_meals_of_kt_foods_with_per_100g_values(session: Session) -> None:
    result = import_day(session, D, DAY)

    meals = {m.meal_type: m for m in session.exec(select(MealLog))}
    items = session.exec(select(MealLogItem)).all()
    egg, toast, milk = foods(session)["kt:g-egg"], foods(session)["kt:g-toast"], foods(session)["kt:g-milk"]
    assert (result.items, result.foods_created, result.warnings) == (4, 4, [])
    assert set(meals) == {"breakfast", "lunch", "second_dinner"}
    assert {m.source for m in meals.values()} == {"kaloricke_tabulky"}
    assert sorted(i.amount_g for i in items) == [36, 125, 200, 200]
    assert (egg.source, egg.name_cs, round(egg.kcal, 1), round(egg.protein_g, 2)) == (
        "kaloricke_tabulky",
        "vejce slepičí",
        151.1,
        12.39,
    )
    assert egg.micronutrients == {"sodium_mg": 138.889, "calcium_mg": 53.889}
    assert egg.fiber_g is None  # unknown stays unknown
    assert round(toast.kcal) == 421
    assert round(milk.kcal, 1) == 13.3  # 111.7 kJ per 200 ml


def test_reimporting_a_day_replaces_it_and_reuses_foods(session: Session) -> None:
    import_day(session, D, DAY)
    again = import_day(session, D, DAY)
    import_day(session, D + dt.timedelta(days=1), diary(("Oběd", [entry("x1", "vejce slepičí", "50 x 1 g")])))

    assert again.foods_created == 0
    assert len(session.exec(select(MealLog).where(MealLog.logged_date == D)).all()) == 3
    assert len(session.exec(select(MealLogItem)).all()) == 5
    assert len(foods(session)) == 4


def test_days_logged_in_the_app_get_the_kt_meals_next_to_them(session: Session) -> None:
    manual = MealLog(logged_date=D, meal_type="lunch")
    session.add(manual)
    session.commit()

    result = import_day(session, D, DAY)
    again = import_day(session, D, DAY)

    assert not result.skipped and result.items == again.items > 0
    assert "zapsaná v aplikaci" in result.warnings[0]
    meals = session.exec(select(MealLog).where(MealLog.logged_date == D)).all()
    assert manual.id in {m.id for m in meals}
    assert len(meals) == 1 + 3  # the app's meal stays, KT's three are replaced (not doubled) on a re-import
    assert len(session.exec(select(MealLogItem)).all()) == result.items


def test_unusable_entries_become_warnings(session: Session) -> None:
    result = import_day(
        session,
        D,
        diary(("Oběd", [entry("a", "voda", "1 sklenice"), entry("b", "bez id", "100 g", guid=None),
                        entry("c", "bez tuku", "100 g", guid="g-x", fat=None)])),
    )  # fmt: skip

    assert result.items == 0
    assert [w.split(" ", 1)[1] for w in result.warnings] == [
        "'voda' – neznámé množství '1 sklenice'",
        "'bez id' bez ID potraviny, přeskočeno",
        "'bez tuku' nemá kcal/bílkoviny/sacharidy/tuky, přeskočeno",
    ]


def test_weights_fill_only_days_without_one(session: Session) -> None:
    session.add(DailyMetric(date=D, weight_kg=80.0))
    session.commit()
    snapshot = Snapshot.model_validate(
        {
            "type": "weight",
            "values": [
                {"from": 1760047200000, "value": 85.9},  # 2025-10-10 00:00 Prague
                {"from": 1791583200000, "value": 81.2},  # 2026-10-10 00:00 Prague
            ],
        }
    )

    filled = import_weights(session, snapshot)

    assert filled == 1
    assert session.get(DailyMetric, dt.date(2025, 10, 10)).weight_kg == 85.9
    assert session.get(DailyMetric, D).weight_kg == 80.0


class FakeKT:
    def __init__(self, diaries: dict[dt.date, Diary], fail_on: dt.date | None = None, expire_once: bool = False):
        self.diaries, self.fail_on, self.expire_once = diaries, fail_on, expire_once
        self.logins, self.requested, self.closed = 0, [], False

    async def login(self, email: str, password: str) -> None:
        self.logins += 1

    async def get_diary(self, day: dt.date) -> Diary:
        self.requested.append(day)
        if self.expire_once:
            self.expire_once = False
            raise AuthError("expired")
        if day == self.fail_on:
            raise RuntimeError("KT is down")
        return self.diaries.get(day, diary())

    async def get_snapshot(self, metric, date_from: dt.date, date_to: dt.date) -> Snapshot:
        return Snapshot.model_validate({"type": "weight", "values": []})

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def factory(session: Session):
    @contextmanager
    def make() -> Iterator[Session]:
        yield session

    return make


def test_the_job_imports_the_range_relogs_in_and_resumes_after_an_error(session: Session, factory) -> None:
    days = [D, D + dt.timedelta(days=1), D + dt.timedelta(days=2)]
    prepare(session, days[0], days[-1])
    failing = FakeKT({D: DAY}, fail_on=days[1], expire_once=True)

    asyncio.run(run_import(failing, factory, ("e", "p"), interval=0))
    state = session.get(KTImportState, 1)
    assert (state.status, state.next_day, state.days_done, failing.logins, failing.closed) == (
        "error",
        days[1],
        1,
        2,
        True,
    )
    assert state.last_error == "KT is down"

    prepare(session, days[0], days[-1])  # same range: continue from the cursor
    healthy = FakeKT({})
    asyncio.run(run_import(healthy, factory, ("e", "p"), interval=0))
    state = session.get(KTImportState, 1)
    assert healthy.requested == days[1:]
    assert (state.status, state.days_done, state.items_imported, state.foods_created) == ("done", 3, 4, 4)


def test_import_endpoint_guards_and_starts(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(nutrition_router, "start_kt_import", lambda: started.append(True))
    monkeypatch.setattr(kt_import, "is_running", lambda: False)
    monkeypatch.setattr(settings, "kaloricketabulky_email", None)
    url = "/api/nutrition/import/kaloricke-tabulky"

    assert client.post(url, json={"date_from": "2026-01-01"}).status_code == 503
    monkeypatch.setattr(settings, "kaloricketabulky_email", "me@example.com")
    monkeypatch.setattr(settings, "kaloricketabulky_password", "secret")
    assert client.post(url, json={"date_from": "2999-01-01"}).status_code == 422
    response = client.post(url, json={"date_from": "2026-01-01", "date_to": "2026-01-31"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["next_day"], body["configured"]) == ("running", "2026-01-01", True)
    assert started == [True]
    assert client.get(url).json()["range_to"] == "2026-01-31"


def test_recipes_that_change_keep_each_days_exact_values_and_the_food_follows_the_newest(
    client: TestClient, session: Session
) -> None:
    """E16: a user's own KT recipe has a different composition every day; history must match KT 1:1."""

    def recipe(protein: float, kcal: str) -> Diary:
        item = entry("r", "Řecký protein", "270 x 1 g", guid="g-recipe", energy=kcal, protein=protein,
                     carbohydrate=11.8, fat=10.56)  # fmt: skip
        return diary(("Odpolední svačina", [item]))

    import_day(session, D, recipe(40.0, "304"))
    import_day(session, D - dt.timedelta(days=1), recipe(27.0, "250"))  # an older day imported later

    def day_totals(day: dt.date) -> tuple[float, float]:
        totals = client.get("/api/nutrition/day", params={"date": day.isoformat()}).json()["totals"]
        return totals["kcal"], totals["protein_g"]

    assert day_totals(D) == (304, 40)
    assert day_totals(D - dt.timedelta(days=1)) == (250, 27)
    # The food follows the newest day, not the older day imported later
    assert round(foods(session)["kt:g-recipe"].protein_g, 2) == 14.81
