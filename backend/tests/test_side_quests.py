import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.models.habits import Habit, HabitLog
from app.models.side_quests import SideQuest
from app.services import quests as qs
from app.services import rpg
from app.services.ai_tools import ToolContext, build_coach_tools
from app.services.badges import compute_badges
from app.timeutils import today

ADDED = dt.datetime(2026, 10, 1, 12, tzinfo=dt.UTC)


def d(day: int, month: int = 10) -> dt.date:
    return dt.date(2026, month, day)


@pytest.fixture
def empty(session: Session) -> Session:
    for model in (SideQuest, Habit):
        session.exec(delete(model))
    session.commit()
    return session


def quest(session: Session, title: str, category: str = "learn", duration: str = "day", **fields) -> SideQuest:
    row = SideQuest(title=title, category=category, duration=duration, **{"created_at": ADDED, **fields})
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_seeded_trips(session: Session) -> None:
    trips = session.exec(select(SideQuest).where(SideQuest.category == "trip")).all()
    assert len(trips) == 95
    macocha = next(q for q in trips if q.title == "Macocha a Punkevní jeskyně")
    assert (macocha.duration, macocha.travel_minutes, macocha.distance_km) == ("day", 25, 20)


def test_seeded_list(session: Session) -> None:
    rows = session.exec(select(SideQuest).where(SideQuest.category != "trip")).all()
    assert len(rows) == 172
    assert len({r.title for r in rows}) == len(rows)
    assert sum(r.done_before_app for r in rows) == 7
    assert {r.duration for r in rows} == {"moment", "day", "weekend", "week", "month"}
    assert {r.category for r in rows} == {"learn", "skill", "make", "food", "move", "explore", "people", "self", "home"}


def test_xp_by_duration_and_category_skill(empty: Session) -> None:
    quest(empty, "Dokument", "learn", "moment", done_on=d(5))
    quest(empty, "Macocha", "trip", "day", done_on=d(6))
    quest(empty, "Kvas", "food", "week", done_on=d(7))
    quest(empty, "Starý", "make", "month", done_before_app=True)  # done before the app: no XP
    quest(empty, "Dávno", "make", "day", done_on=d(1, 9))  # a month before it was added: no XP
    quest(empty, "Otevřený", "explore", "weekend")
    ledger = rpg.build_ledger(empty, d(10))
    gained = [(e.date, e.amount, e.text, e.skills) for e in ledger.entries if e.kind == "side_quest"]
    assert gained == [
        (d(5), 20, "Side quest: Dokument (Chvilka)", {"mind": 20}),
        (d(6), 50, "Side quest: Macocha (1 den)", {"adventure": 50}),
        (d(7), 250, "Side quest: Kvas (Týden)", {"nutrition": 250}),
    ]


def test_weekly_quest_any_duration(empty: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qs, "SIDE_QUEST_FROM", d(5))
    h = Habit(title="Postel", start_date=d(28, 9))
    empty.add(h)
    empty.commit()
    empty.add_all([HabitLog(habit_id=h.id, date=d(28, 9) + dt.timedelta(days=i)) for i in range(23)])
    quest(empty, "Dokument", "learn", "moment", done_on=d(14))
    quest(empty, "Macocha", "trip")
    ledger = rpg.build_ledger(empty, d(20))
    side = [(e.date, e.kind, e.amount, e.text) for e in ledger.entries if "side quest" in e.text.lower()]
    assert (d(11), "quest_failed", 0, "Výprava nesplněna: Dokonči side quest (0/1 ×)") in side  # week of 5. 10.
    assert (d(14), "quest", 80, "Výprava splněna: Dokonči side quest") in side  # week of 12. 10.
    assert next(q for q in ledger.quests if q.key == "side").done_on is None  # this week: still open
    # the week before SIDE_QUEST_FROM has no side quest
    assert not any(e.date < d(5) for e in ledger.entries if "Dokonči side quest" in e.text)


def test_badges(empty: Session) -> None:
    for i in range(10):
        quest(
            empty, f"Q{i}", done_on=d(1, 8) + dt.timedelta(weeks=i), created_at=dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
        )
    quest(empty, "Blízko", "trip", travel_minutes=30, done_before_app=True)
    quest(empty, "Daleko", "trip", travel_minutes=90)
    ledger = rpg.build_ledger(empty, d(20))
    badges = {b.key: b for b in compute_badges(empty, ledger, [], d(20))}
    assert badges["side_first"].unlocked_on == d(1, 8)
    assert badges["side_10"].unlocked_on == d(1)  # "Blízko" (done before the app) counts from 1. 10.
    assert badges["side_weeks"].unlocked_on == d(1, 8) + dt.timedelta(weeks=9)
    assert badges["side_50"].progress == "11 / 50"
    assert badges["trips_near"].unlocked_on == ADDED.date()


def test_api(client: TestClient, empty: Session) -> None:
    created = client.post("/api/side-quests", json={"title": " Naučit se žonglovat ", "category": "learn"})
    assert created.status_code == 201
    body = created.json()
    assert (body["title"], body["duration"], body["xp"], body["done"]) == ("Naučit se žonglovat", "day", 50, False)
    qid = body["id"]
    assert client.post("/api/side-quests", json={"title": "X", "category": "nope"}).status_code == 422
    future = str(today() + dt.timedelta(days=3))
    assert client.patch(f"/api/side-quests/{qid}", json={"done_on": future}).status_code == 422

    started = client.patch(f"/api/side-quests/{qid}", json={"active": True, "duration": "week"}).json()
    assert started["active"] and started["xp"] == 250
    done = client.patch(
        f"/api/side-quests/{qid}", json={"done_on": str(today()), "memory": "Tři míčky", "rating": 4}
    ).json()
    assert done["done"] and not done["active"] and done["xp"] == 250

    board = client.get("/api/side-quests").json()
    assert [i["title"] for i in board["items"]] == ["Naučit se žonglovat"]
    assert board["week"]["done"] == 1 and board["week"]["titles"] == ["Naučit se žonglovat"]
    assert board["xp_total"] == 250
    assert [c["key"] for c in board["categories"]][:3] == ["learn", "skill", "make"]

    undone = client.patch(f"/api/side-quests/{qid}", json={"done_on": None}).json()
    assert not undone["done"] and undone["memory"] == "Tři míčky"
    assert client.delete(f"/api/side-quests/{qid}").status_code == 204
    assert client.delete(f"/api/side-quests/{qid}").status_code == 404


def test_coach_tools(empty: Session) -> None:
    quest(empty, "Macocha a Punkevní jeskyně", "trip", travel_minutes=25)
    quest(empty, "Upéct chleba", "food")
    now = dt.datetime.combine(d(21), dt.time(12), tzinfo=dt.UTC)
    tools = {fn.__name__: fn for fn in build_coach_tools(ToolContext(session=empty, now=now))}
    listed = tools["get_side_quests"](category="trip")
    assert [i["title"] for i in listed["items"]] == ["Macocha a Punkevní jeskyně"]
    assert listed["items"][0]["drive_min"] == 25

    result = tools["complete_side_quests"](["macocha a punkevni jeskyne", "chleba"], memory="Super")
    assert result["saved"] == ["Macocha a Punkevní jeskyně"]
    assert result["not_saved"][0]["candidates"] == ["Upéct chleba"]
    assert tools["get_side_quests"]()["this_week_done"] == ["Macocha a Punkevní jeskyně"]
