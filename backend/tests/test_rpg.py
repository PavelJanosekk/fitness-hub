import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

from app.config import settings
from app.models.habits import Habit, HabitLog
from app.models.rpg import RpgPause
from app.models.running import Activity
from app.services import habits as hs
from app.services import rpg

MONDAY = dt.date(2026, 10, 19)  # the week 12.-18. 10. is finished


def d(day: int, month: int = 10) -> dt.date:
    return dt.date(2026, month, day)


@pytest.fixture
def empty(session: Session) -> Session:
    session.exec(delete(Habit))
    session.commit()
    return session


def habit(session: Session, title: str, start: dt.date, done: list[dt.date]) -> Habit:
    h = Habit(title=title, start_date=start)
    session.add(h)
    session.commit()
    session.refresh(h)
    session.add_all([HabitLog(habit_id=h.id, date=day) for day in done])
    session.commit()
    return h


def run(session: Session, day: dt.date, km: float) -> None:
    start = dt.datetime.combine(day, dt.time(8), tzinfo=settings.tz)
    session.add(Activity(start_time=start, activity_type="Run", distance_meters=km * 1000, duration_seconds=3600))
    session.commit()


def kinds(ledger: rpg.Ledger, day: dt.date) -> list[tuple[str, int]]:
    return [(e.kind, e.amount) for e in ledger.entries if e.date == day]


def test_levels_and_titles() -> None:
    assert rpg.level_of(0) == 1 and rpg.level_of(99) == 1 and rpg.level_of(100) == 2
    assert rpg.level_start(3) == 100 + 283
    assert rpg.level_of(-500) == 1
    assert rpg.title_of(1) == "Učeň" and rpg.title_of(12) == "Vytrvalec"
    assert rpg.next_title(12) == (15, "Maratonec")
    assert rpg.multiplier_for(1) == 1.0 and rpg.multiplier_for(2) == 1.1 and rpg.multiplier_for(40) == 1.5


def test_forgiven_day_then_day_penalty_and_week_ok(empty: Session) -> None:
    week = [d(12), d(15), d(16), d(17), d(18)]  # 13. and 14. missed
    habit(empty, "A", d(12), week)
    habit(empty, "B", d(12), week)

    ledger = rpg.build_ledger(empty, MONDAY)

    assert ("forgiven", 0) in kinds(ledger, d(13))  # the month's first missed day
    assert ("day_penalty", -20) in kinds(ledger, d(14))
    assert ("perfect_day", 50) in kinds(ledger, d(12))
    sunday = [e for e in ledger.entries if e.date == d(18) and e.kind == "week_ok"]
    assert sunday and "83 %" in sunday[0].text  # 10 of 12, the forgiven day left out
    assert ledger.total == 5 * 20 + 5 * 50 - 20
    assert ledger.week_streak == 1


def test_streak_multiplier_then_week_penalty_resets_it(empty: Session) -> None:
    days = [d(28, 9) + dt.timedelta(days=i) for i in range(14)] + [d(12)]
    habit(empty, "A", d(28, 9), days)

    ledger = rpg.build_ledger(empty, MONDAY)

    # two qualifying weeks -> x1.1 from Monday 12. 10.: 60 XP of gains get +6
    assert ("multiplier", 6) in kinds(ledger, d(12))
    assert ("forgiven", 0) in kinds(ledger, d(13))
    assert all(("day_penalty", -20) in kinds(ledger, d(day)) for day in range(14, 19))
    penalty = next(e for e in ledger.entries if e.kind == "week_penalty")
    assert penalty.amount == -100 and "série 2 končí" in penalty.text and penalty.date == d(18)
    assert ledger.week_streak == 0 and ledger.multiplier == 1.0
    assert ledger.total == 14 * 60 + 66 - 5 * 20 - 100


def test_penalties_take_the_level_down(empty: Session) -> None:
    run(empty, d(12), 22)  # 110 + 25 for a long run -> level 2
    habit(empty, "A", d(12), [])

    ledger = rpg.build_ledger(empty, MONDAY)

    level_events = [e.kind for e in ledger.entries if e.kind.startswith("level_")]
    assert level_events == ["level_up", "level_down"]
    assert ledger.total == 135 - 6 * 20 - 100  # 12. forgiven, 13.-18. below 30 %, the week below 60 %
    assert rpg.level_of(ledger.total) == 1


def test_pause_counts_for_nothing_and_keeps_streaks(empty: Session) -> None:
    a = habit(empty, "A", d(12), [d(12), d(16), d(17), d(18)])
    run(empty, d(14), 10)
    empty.add(RpgPause(start_date=d(13), end_date=d(15)))
    empty.commit()

    ledger = rpg.build_ledger(empty, MONDAY)

    assert kinds(ledger, d(13)) == [("pause", 0)]
    assert kinds(ledger, d(14)) == []  # no run XP, no penalty
    assert not any(e.kind in {"day_penalty", "week_penalty", "forgiven"} for e in ledger.entries)
    board = hs.load_board(empty, end=d(18))
    a_days = next(item for item in board if item.habit.id == a.id)
    assert hs.current_streak(a_days, d(18)) == 4  # steps over the paused days
    assert hs.completion(a_days, d(12), d(18)) == (4, 4)


def test_character_history_and_pauses_api(client: TestClient, empty: Session) -> None:
    character = client.get("/api/rpg/character").json()
    assert {"level", "title", "xp_total", "next_level_xp", "multiplier", "paused"} <= character.keys()

    created = client.post("/api/rpg/pauses", json={"start_date": "2026-10-01", "end_date": "2026-10-03"})
    assert created.status_code == 201
    assert client.post("/api/rpg/pauses", json={"start_date": "2026-10-03"}).status_code == 409
    backwards = {"start_date": "2026-10-05", "end_date": "2026-10-04"}
    assert client.post("/api/rpg/pauses", json=backwards).status_code == 422
    open_pause = client.post("/api/rpg/pauses", json={"start_date": "2026-10-04"}).json()
    ended = client.patch(f"/api/rpg/pauses/{open_pause['id']}", json={"end_date": "2026-10-06"}).json()
    assert ended["end_date"] == "2026-10-06"
    assert [p["start_date"] for p in client.get("/api/rpg/pauses").json()] == ["2026-10-04", "2026-10-01"]
    assert client.delete(f"/api/rpg/pauses/{created.json()['id']}").status_code == 204
    assert isinstance(client.get("/api/rpg/history?days=7").json(), list)
