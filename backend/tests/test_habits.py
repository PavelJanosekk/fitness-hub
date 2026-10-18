import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.config import settings
from app.models.body import DailyMetric
from app.models.gym import Workout, WorkoutSet
from app.models.habits import AutoRule, Habit, HabitLog
from app.models.running import Activity
from app.services import habits as svc
from app.timeutils import today

SUNDAY = dt.date(2026, 10, 18)


def d(day: int, month: int = 10) -> dt.date:
    return dt.date(2026, month, day)


def at(day: int, hour: int) -> dt.datetime:
    """A moment on a local (Prague) October day."""
    return dt.datetime(2026, 10, day, hour, tzinfo=settings.tz)


@pytest.fixture
def empty(session: Session) -> Session:
    """No habits: the seeded ones from migration 0012 are removed (rolled back after the test)."""
    session.exec(delete(Habit))
    session.commit()
    return session


def add_habit(session: Session, **fields) -> Habit:
    habit = Habit(**{"title": "Ustlat postel", "start_date": d(1), **fields})
    session.add(habit)
    session.commit()
    session.refresh(habit)
    return habit


def days_of(habit: Habit, done: list[dt.date]) -> svc.HabitDays:
    return svc.HabitDays(habit, manual=set(done))


def test_migration_seeds_the_sheet_routine_with_its_ticks(session: Session) -> None:
    habits = {h.title: h for h in session.exec(select(Habit)).all()}

    assert len(habits) == 13
    assert habits["Nepodvádět dietu"].is_bonus and habits["Nepodvádět dietu"].points == 2
    assert habits["Cvičení"].auto_rule == AutoRule.gym_or_activity
    assert habits["Úklid · koupelna"].frequency == "weekly"
    creatine = session.exec(select(HabitLog.date).where(HabitLog.habit_id == habits["Kreatin + vitamíny"].id)).all()
    assert sorted(creatine) == [d(14), d(15), d(16), d(17)]


def test_day_state_is_idempotent(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)
    url = f"/api/habits/{habit.id}/days/{today().isoformat()}"

    for _ in range(2):
        assert client.put(url, json={"done": True}).json()["done"] is True
    assert len(empty.exec(select(HabitLog)).all()) == 1
    for _ in range(2):
        assert client.put(url, json={"done": False}).status_code == 200
    assert empty.exec(select(HabitLog)).all() == []


def test_day_state_rejects_future_and_unknown_and_extends_start(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty, start_date=today())
    future = today() + dt.timedelta(days=2)
    earlier = today() - dt.timedelta(days=5)

    assert client.put(f"/api/habits/{habit.id}/days/{future}", json={"done": True}).status_code == 422
    assert client.put(f"/api/habits/999999/days/{today()}", json={"done": True}).status_code == 404
    assert client.put(f"/api/habits/{habit.id}/days/{earlier}", json={"done": True}).status_code == 200
    empty.refresh(habit)
    assert habit.start_date == earlier


def test_create_normalizes_and_appends(client: TestClient, empty: Session) -> None:
    first = client.post("/api/habits", json={"title": "  Anki  ", "weekly_target": 3}).json()
    weekly = client.post(
        "/api/habits",
        json={
            "title": "Posilovna",
            "frequency": "weekly",
            "weekly_target": 3,
            "is_bonus": True,
            "auto_rule": "gym_workout",
            "auto_threshold": 5,
        },
    ).json()

    assert first["title"] == "Anki" and first["weekly_target"] == 1 and first["start_date"] == today().isoformat()
    assert weekly["weekly_target"] == 3 and weekly["is_bonus"] is False and weekly["auto_threshold"] is None
    assert weekly["position"] > first["position"]
    assert client.post("/api/habits", json={"title": "   "}).status_code == 422
    assert client.post("/api/habits", json={"title": "X", "points": 4}).status_code == 422


def test_patch_archives_restores_and_edits(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)

    archived = client.patch(f"/api/habits/{habit.id}", json={"archived": True, "title": "Postel"}).json()
    assert archived["archived_at"] is not None and archived["title"] == "Postel"
    again = client.patch(f"/api/habits/{habit.id}", json={"archived": True}).json()
    assert again["archived_at"] == archived["archived_at"]  # archiving twice keeps the first date
    restored = client.patch(f"/api/habits/{habit.id}", json={"archived": False, "skill": "discipline"}).json()
    assert restored["archived_at"] is None and restored["skill"] == "discipline"
    assert client.patch("/api/habits/999999", json={"title": "X"}).status_code == 404


def test_reorder_needs_every_habit(client: TestClient, empty: Session) -> None:
    a, b = add_habit(empty, title="A"), add_habit(empty, title="B")

    assert client.put("/api/habits/order", json={"ids": [b.id]}).status_code == 422
    assert client.put("/api/habits/order", json={"ids": [b.id, a.id]}).status_code == 204
    board = client.get("/api/habits/board").json()
    assert [h["title"] for h in board["habits"]] == ["B", "A"]


def test_delete_removes_history(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)
    empty.add(HabitLog(habit_id=habit.id, date=d(2)))
    empty.commit()

    assert client.delete(f"/api/habits/{habit.id}").status_code == 204
    assert empty.exec(select(HabitLog)).all() == []


def test_daily_streak_survives_an_unticked_today_and_stops_at_start(empty: Session) -> None:
    habit = add_habit(empty, start_date=d(15))

    assert svc.current_streak(days_of(habit, [d(15), d(16), d(17)]), SUNDAY) == 3
    assert svc.current_streak(days_of(habit, [d(15), d(16), d(17), d(18)]), SUNDAY) == 4
    assert svc.current_streak(days_of(habit, [d(14), d(15), d(16)]), SUNDAY) == 0  # yesterday missed
    habit.start_date = d(16)
    assert svc.current_streak(days_of(habit, [d(14), d(15), d(16), d(17)]), SUNDAY) == 2
    assert svc.best_streak(days_of(habit, [d(16), d(17), d(10), d(11), d(12)]), SUNDAY) == 2


def test_weekly_target_streak_and_rate(empty: Session) -> None:
    habit = add_habit(empty, frequency="weekly", weekly_target=2, start_date=d(28, 9))
    # weeks: 28.9. met (2), 5.10. met (2), 12.10. one so far (current, not met yet)
    done = [d(29, 9), d(1), d(6), d(8), d(14)]

    assert svc.current_streak(days_of(habit, done), SUNDAY) == 2
    assert svc.completion(days_of(habit, done), d(28, 9), SUNDAY) == (2, 2)  # the open week is left out
    assert svc.current_streak(days_of(habit, [*done, d(16)]), SUNDAY) == 3
    assert svc.completion(days_of(habit, [*done, d(16)]), d(28, 9), SUNDAY) == (3, 3)


def test_daily_rate_ignores_days_before_start_and_after_archiving(empty: Session) -> None:
    habit = add_habit(empty, start_date=d(10), archived_at=at(15, 9))

    assert svc.completion(days_of(habit, [d(10), d(11), d(14)]), d(1), SUNDAY) == (3, 5)  # 10.-14.


def test_routine_day_and_week_streak_leave_bonus_out(empty: Session) -> None:
    bed = add_habit(empty, title="Postel", start_date=d(28, 9))
    anki = add_habit(empty, title="Anki", start_date=d(28, 9))
    diet = add_habit(empty, title="Dieta", is_bonus=True, points=2, start_date=d(28, 9))
    every_day = [d(28, 9) + dt.timedelta(days=i) for i in range(21)]
    board = [days_of(bed, every_day), days_of(anki, every_day[7:]), days_of(diet, [])]

    assert svc.routine_day(board, d(29, 9)) == (1, 2)
    # week of 28.9. = 50 % (below 60), 5.10. and 12.10. = 100 %
    assert svc.routine_week_streak(board, SUNDAY) == 2


def test_auto_rules_from_workouts_activities_and_steps(empty: Session, exercises: dict[str, int]) -> None:
    workout = Workout(id=uuid.uuid4(), name="Push", started_at=at(16, 18))
    empty_workout = Workout(id=uuid.uuid4(), name="Prázdný", started_at=at(15, 18))
    empty.add_all([workout, empty_workout])
    empty.flush()
    empty.add(
        WorkoutSet(workout_id=workout.id, exercise_id=exercises["Bench Press (Barbell)"], exercise_order=1, set_order=1)
    )
    empty.add_all(
        [
            Activity(start_time=at(18, 9), activity_type="Run", distance_meters=18200, duration_seconds=6000),
            Activity(start_time=at(17, 9), activity_type="Walk", distance_meters=3000, duration_seconds=2000),
            DailyMetric(date=d(17), steps=12500),
            DailyMetric(date=d(18), steps=9000, weight_kg=84.2),
        ]
    )
    empty.commit()

    def auto(rule: AutoRule, threshold: float | None = None) -> dict[dt.date, str]:
        return svc.auto_days(empty, rule, threshold, d(14), SUNDAY)

    assert auto(AutoRule.gym_workout) == {d(16): "Gym · Push"}  # the workout without sets doesn't count
    assert auto(AutoRule.activity) == {d(18): "Běh 18,2 km"}  # walks don't count
    assert auto(AutoRule.gym_or_activity).keys() == {d(16), d(18)}
    assert auto(AutoRule.steps) == {d(17): "12 500 kroků"}
    assert auto(AutoRule.steps, 8000).keys() == {d(17), d(18)}
    assert auto(AutoRule.weight_logged) == {d(18): "84,2 kg"}
    assert auto(AutoRule.protein) == {}  # no target set


def test_board_returns_manual_and_auto_days(client: TestClient, empty: Session) -> None:
    current = today()
    habit = add_habit(empty, title="Kroky", auto_rule="steps", start_date=current - dt.timedelta(days=3))
    other = add_habit(empty, title="Postel", start_date=current - dt.timedelta(days=3))
    empty.add_all(
        [
            HabitLog(habit_id=other.id, date=current),
            DailyMetric(date=current - dt.timedelta(days=1), steps=15000),
            DailyMetric(date=current - dt.timedelta(days=10), steps=15000),  # before the habit existed
        ]
    )
    empty.commit()

    body = client.get("/api/habits/board").json()

    assert body["today"] == current.isoformat()
    by_title = {h["title"]: h for h in body["habits"]}
    assert by_title["Postel"]["done"] == [current.isoformat()]
    assert list(by_title["Kroky"]["auto"]) == [(current - dt.timedelta(days=1)).isoformat()]
    assert habit.id == by_title["Kroky"]["id"]


def test_resolve_habit_exact_and_fuzzy(empty: Session) -> None:
    bed = add_habit(empty, title="Ustlat postel")
    add_habit(empty, title="Úklid · koupelna")
    add_habit(empty, title="Starý návyk", archived_at=at(1, 9))

    exact, _ = svc.resolve_habit(empty, "ustlat POSTEL")
    assert exact is not None and exact.id == bed.id
    none, candidates = svc.resolve_habit(empty, "koupelna")
    assert none is None and candidates[0][0].title == "Úklid · koupelna"
    assert svc.resolve_habit(empty, "Starý návyk") == (None, [])


# --- Coach tools ---------------------------------------------------------------------------------

NOW = dt.datetime(2026, 10, 18, 9, 0, tzinfo=dt.UTC)  # Sunday 11:00 in Prague


def coach_tool(session: Session, name: str):
    from app.services.ai_tools import ToolContext, build_coach_tools

    return next(fn for fn in build_coach_tools(ToolContext(session=session, now=NOW)) if fn.__name__ == name)


def test_habit_catalog_lists_active_habits(empty: Session) -> None:
    from app.services.ai_tools import habit_catalog

    add_habit(empty, title="Postel")
    add_habit(empty, title="Koupelna", frequency="weekly", weekly_target=2, position=1)
    add_habit(empty, title="Dieta", is_bonus=True, auto_rule="protein", position=2)
    add_habit(empty, title="Staré", archived_at=at(1, 9), position=3)

    assert habit_catalog(empty).splitlines() == [
        "- Postel [denně]",
        "- Koupelna [týdně 2×]",
        "- Dieta [denně, bonus, plní se i automaticky z dat]",
    ]


def test_set_habits_done_saves_exact_titles_only(empty: Session) -> None:
    from google.genai import _extra_utils

    bed = add_habit(empty, title="Ustlat postel")
    add_habit(empty, title="Kreatin + vitamíny")
    tool = coach_tool(empty, "set_habits_done")

    result = _extra_utils.invoke_function_from_dict_args({"habit_titles": ["ustlat postel", "kreatin"]}, tool)

    assert result["saved"] == ["Ustlat postel"] and result["date"] == "2026-10-18"
    assert result["not_saved"] == [{"input": "kreatin", "candidates": ["Kreatin + vitamíny"]}]
    assert empty.exec(select(HabitLog.habit_id, HabitLog.date)).all() == [(bed.id, SUNDAY)]
    assert "error" in tool(habit_titles=["Ustlat postel"], date="2026-10-19")


def test_set_habits_done_unticks_a_whole_week_of_a_weekly_habit(empty: Session) -> None:
    room = add_habit(empty, title="Úklid · koupelna", frequency="weekly")
    empty.add_all([HabitLog(habit_id=room.id, date=d(13)), HabitLog(habit_id=room.id, date=d(9))])
    empty.commit()

    result = coach_tool(empty, "set_habits_done")(habit_titles=["Úklid · koupelna"], done=False)

    assert result["saved"] == ["Úklid · koupelna"]
    assert empty.exec(select(HabitLog.date)).all() == [d(9)]  # the previous week stays


def test_habit_summary_rates_streaks_and_routine(empty: Session) -> None:
    bed = add_habit(empty, title="Postel", start_date=d(12))
    anki = add_habit(empty, title="Anki", start_date=d(12), position=1)
    add_habit(empty, title="Koupelna", frequency="weekly", start_date=d(5), position=2)
    empty.add_all(
        [HabitLog(habit_id=bed.id, date=d(day)) for day in (12, 13, 14, 15, 16, 17)]
        + [HabitLog(habit_id=anki.id, date=d(day)) for day in (12, 14)]
    )
    empty.commit()

    result = coach_tool(empty, "get_habit_summary")(days=7)

    habits = {h["title"]: h for h in result["habits"]}
    assert habits["Postel"]["current_streak"] == 6 and habits["Postel"]["done_today"] is False
    assert (habits["Postel"]["done"], habits["Postel"]["scheduled"]) == (6, 7)
    assert habits["Anki"]["best_streak"] == 1 and habits["Anki"]["last_done"] == "2026-10-14"
    # the window only holds the current week, which is still open: no rate yet
    assert habits["Koupelna"]["scheduled"] == 0 and "rate_pct" not in habits["Koupelna"]
    assert habits["Koupelna"]["done_this_week"] == 0
    routine = result["daily_routine"]
    assert routine["days_counted"] == 6  # 12.-17.; today is still open
    assert routine["perfect_days"] == 2 and routine["avg_pct"] == 67
    assert routine["by_weekday_pct"]["pondělí"] == 100
