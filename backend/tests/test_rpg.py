import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

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
    # + the week of 5. 10.'s habit quest for A (the weakest habit of the 7 days before), done on 9. 10.
    assert ledger.total == 14 * 60 + 60 + 66 - 5 * 20 - 100


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


def test_skills_get_their_xp(empty: Session, exercises: dict[str, int]) -> None:
    import uuid

    from app.models.gym import Workout, WorkoutSet

    cviceni = Habit(title="Cvičení", start_date=d(12), skill="body", points=1)
    anki = Habit(title="Anki", start_date=d(12), skill="mind", points=2)
    empty.add_all([cviceni, anki])
    empty.commit()
    empty.add_all([HabitLog(habit_id=cviceni.id, date=d(12)), HabitLog(habit_id=anki.id, date=d(12))])
    workout = Workout(id=uuid.uuid4(), name="Push", started_at=dt.datetime(2026, 10, 12, 18, tzinfo=settings.tz))
    empty.add(workout)
    empty.flush()
    empty.add_all(
        [
            WorkoutSet(
                workout_id=workout.id, exercise_id=exercises["Bench Press (Barbell)"], exercise_order=1, set_order=i
            )
            for i in (1, 2, 3)
        ]
    )
    empty.commit()
    run(empty, d(12), 8)

    skills = {k: s.xp for k, s in rpg.build_ledger(empty, d(13)).skills.items()}

    # Cvičení 10 split 5/5, Anki 20, perfect day 50 -> Disciplína, 3 sets x 2 -> Síla, 8 km x 5 -> Výdrž
    assert skills == {"strength": 5 + 6, "endurance": 5 + 40, "mind": 20, "discipline": 50}
    habits_entries = [e.text for e in rpg.build_ledger(empty, d(13)).entries if e.kind == "habits"]
    assert sorted(habits_entries) == ["Návyky (Mysl): Anki", "Návyky (Tělo): Cvičení"]


def test_idle_skill_rusts_weekly_and_pause_freezes_it(empty: Session) -> None:
    habit(empty, "A", d(1, 9), [d(1, 9) + dt.timedelta(days=i) for i in range(49)])
    run(empty, d(1, 9), 10)  # Výdrž 50 XP, then nothing
    empty.add(RpgPause(start_date=d(10, 9), end_date=d(16, 9)))
    empty.commit()

    ledger = rpg.build_ledger(empty, MONDAY)

    rust = [(e.date, e.amount) for e in ledger.entries if e.kind == "rust"]
    # idle 2.-9. 9. and from 17. 9. (the pause doesn't count): 21 idle days on 29. 9., then weekly
    assert rust == [(d(29, 9), -20), (d(6), -20), (d(13), -10)]
    endurance = ledger.skills["endurance"]
    assert endurance.xp == 0 and endurance.idle_days >= rpg.RUST_LOSS_DAYS


def test_character_lists_all_skills(client: TestClient, empty: Session) -> None:
    skills = client.get("/api/rpg/character").json()["skills"]

    assert [s["key"] for s in skills] == ["strength", "endurance", "nutrition", "discipline", "mind", "home"]
    assert all(s["level"] >= 1 and s["next_level_xp"] > s["level_start_xp"] for s in skills)


def test_marathon_boss_hits_heals_and_defeat(empty: Session) -> None:
    from sqlmodel import delete as sql_delete

    from app.models.coach import Race, TrainingDay, TrainingWeek
    from app.services.boss import marathon_boss

    for model in (Race, TrainingDay, TrainingWeek):
        empty.exec(sql_delete(model))
    race_day = d(1, 11)
    empty.add_all(
        [
            Race(name="Maraton", date=race_day, distance_km=42.195, is_goal_race=True),
            Race(name="Půlmaraton", date=d(25), distance_km=21.1, is_goal_race=False),
            TrainingWeek(week_start=d(5), week_end=d(11), km_min=20, km_max=25),  # no daily schedule
            TrainingWeek(week_start=d(12), week_end=d(18), km_min=10, km_max=12),
            TrainingWeek(week_start=d(26), week_end=race_day, km_min=50, km_max=60),
            TrainingDay(planned_date=d(14), text="Easy 5 km", km_min=5, km_max=5),
            TrainingDay(planned_date=d(15), text="Volno", is_rest=True),
            TrainingDay(planned_date=d(16), text="Easy 6 km", km_min=6, km_max=6),
        ]
    )
    empty.commit()
    run(empty, d(7), 8)  # week 5.-11.: 8 of at least 20 -> heals 12
    run(empty, d(14), 5)  # 16. skipped -> heals 6
    run(empty, d(10), 4)  # a day after a planned day that already had its own run: no effect on the schedule

    boss = marathon_boss(empty, MONDAY)

    assert boss is not None and boss.name == "Maraton" and boss.max_hp == 25 + 12 + 60
    assert (boss.damage_km, boss.heal_km) == (17, 14)  # week 5.-11.: 12 of 20 -> heals 8
    assert boss.hp == 97 - 17 + 14
    assert {e.text for e in boss.events if e.kind == "heal"} == {
        "Týden 5. 10. pod plánem o 8 km",
        "Vynechaný běh pá 16. 10.: Easy 6 km",
    }
    assert boss.status == "active" and boss.days_left == 13

    run(empty, d(17), 6)  # the skipped 16. was only moved by a day: no heal
    assert {e.text for e in marathon_boss(empty, MONDAY).events if e.kind == "heal"} == {
        "Týden 5. 10. pod plánem o 8 km"
    }

    run(empty, race_day, 42.3)
    assert marathon_boss(empty, race_day).status == "defeated"
    assert marathon_boss(empty, race_day).hp == 0


def _workout(session: Session, day: dt.date, exercise_id: int, sets: int) -> None:
    import uuid

    from app.models.gym import Workout, WorkoutSet

    workout = Workout(
        id=uuid.uuid4(), name="Trénink", started_at=dt.datetime.combine(day, dt.time(18), tzinfo=settings.tz)
    )
    session.add(workout)
    session.flush()
    session.add_all(
        [
            WorkoutSet(workout_id=workout.id, exercise_id=exercise_id, exercise_order=1, set_order=i + 1)
            for i in range(sets)
        ]
    )
    session.commit()


def test_weekly_quests_rewards_bonus_and_failures(empty: Session, exercises: dict[str, int]) -> None:
    from sqlmodel import delete as sql_delete

    from app.models.coach import TrainingWeek

    empty.exec(sql_delete(TrainingWeek))
    empty.add(TrainingWeek(week_start=d(12), week_end=d(18), km_min=10, km_max=12))
    from app.models.gym import Exercise

    by_group = {e.muscle_group: e.id for e in empty.exec(select(Exercise)).all()}
    bench, squat = exercises["Bench Press (Barbell)"], exercises["Squat (Barbell)"]
    for day in (d(15, 9), d(22, 9), d(29, 9), d(6)):  # 1 workout a week before -> target 2 (minimum)
        _workout(empty, day, bench, 3)
    for group in ("back", "shoulders", "arms", "core"):  # legs stay the only untrained group
        _workout(empty, d(7), by_group[group], 1)
    weak = habit(empty, "Anki", d(14, 9), [d(14, 9) + dt.timedelta(days=i) for i in range(0, 28, 3)])
    habit(empty, "Postel", d(14, 9), [d(14, 9) + dt.timedelta(days=i) for i in range(35)])
    room = Habit(title="Úklid · koupelna", frequency="weekly", skill="home", start_date=d(14, 9))
    empty.add(room)
    empty.commit()
    # this week: everything done
    run(empty, d(13), 6)
    run(empty, d(15), 5)
    _workout(empty, d(14), squat, 6)  # legs were the weakest group (0 sets before)
    _workout(empty, d(16), bench, 3)
    empty.add_all(
        [HabitLog(habit_id=room.id, date=d(17))]
        + [HabitLog(habit_id=weak.id, date=day) for day in (d(12), d(13), d(14), d(15), d(16))]
    )
    empty.commit()

    ledger = rpg.build_ledger(empty, MONDAY)

    quests = {q.key: q for q in rpg.build_ledger(empty, d(18)).quests}
    assert quests["run"].title == "Uběhni 10 km podle plánu" and quests["run"].done_on == d(15)
    assert quests["gym"].target == 2 and quests["gym"].done_on == d(16)
    assert quests["muscle:legs"].done_on == d(14)
    assert quests["home"].done_on == d(17)
    assert quests[f"habit:{weak.id}"].done_on == d(16)
    this_week = [(e.date, e.kind, e.amount) for e in ledger.entries if e.kind.startswith("quest") and e.date >= d(12)]
    assert (d(17), "quests_all", 100) in this_week
    assert sum(1 for _, kind, _ in this_week if kind == "quest") == 5
    # earlier weeks had open quests (no plan -> no run quest; gym 1 of 2): recorded as failed, no XP
    failed = [e for e in ledger.entries if e.kind == "quest_failed"]
    assert failed and all(e.amount == 0 for e in failed)
    skills = next(
        e.skills for e in ledger.entries if e.kind == "quest" and "koupelna" not in e.text and "byt" in e.text
    )
    assert skills == {"home": 80}


def test_badges(client: TestClient, empty: Session) -> None:
    habit(empty, "A", d(12), [d(12), d(13)])
    run(empty, d(13), 42.5)

    badges = {b["key"]: b for b in client.get("/api/rpg/badges").json()}

    assert badges["perfect_day"]["unlocked_on"] == "2026-10-12"
    assert badges["marathon"]["unlocked_on"] == "2026-10-13"
    assert badges["workouts_100"]["unlocked_on"] is None and badges["workouts_100"]["progress"] == "0 / 100"
    assert badges["streak_30"]["progress"].startswith("nejlepší")


def test_tired_week_after_a_failed_one_until_back_at_60(empty: Session) -> None:
    # week 5.-11.: nothing (below 60 %); week 12.-18.: done from Wednesday on
    habit(empty, "A", d(5), [d(14), d(15), d(16), d(17), d(18)])
    run(empty, d(12), 10)  # 50 XP on the tired Monday

    ledger = rpg.build_ledger(empty, MONDAY)

    assert ("tired", 0) in kinds(ledger, d(12))  # the debuff starts
    assert ("tired", -10) in kinds(ledger, d(12))  # 50 XP x0.8
    # 12. (forgiven? no: October's forgiven day is 5. 10.), 13. missed, 14.-16. done: 3 of 5 = 60 % on 16.
    assert any(kind == "tired_end" for kind, _ in kinds(ledger, d(16)))
    assert not any(kind == "tired" for kind, _ in kinds(ledger, d(17)))


def test_cursed_habit_pays_double_and_costs_when_missed(empty: Session) -> None:
    # missed 8.-11.: 8. is October's forgiven day, the other 3 misses curse it for the next week
    a = habit(empty, "Anki", d(5), [d(5), d(6), d(7)])
    habit(empty, "Postel", d(5), [d(5) + dt.timedelta(days=i) for i in range(14)])
    empty.add_all([HabitLog(habit_id=a.id, date=d(12)), HabitLog(habit_id=a.id, date=d(14))])
    empty.commit()

    ledger = rpg.build_ledger(empty, MONDAY)

    assert ("curse", 0) in kinds(ledger, d(12))
    assert ("curse_done", 10) in kinds(ledger, d(12))
    assert ("curse_missed", -10) in kinds(ledger, d(13))
    assert ("curse_missed", -10) in kinds(ledger, d(15))
    assert rpg.build_ledger(empty, d(16)).cursed == ["Anki"]
