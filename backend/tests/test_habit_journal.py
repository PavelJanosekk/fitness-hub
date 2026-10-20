"""Habit journal + Dovednosti (E37): log modes, entries on ticks, abilities and their XP."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.models.habits import Ability, Habit, HabitLog
from app.models.rpg import RpgPause
from app.services import abilities as ab
from app.services import habits as hs
from app.services import rpg
from app.timeutils import today


def d(day: int, month: int = 10) -> dt.date:
    return dt.date(2026, month, day)


@pytest.fixture
def empty(session: Session) -> Session:
    session.exec(delete(Habit))
    session.exec(delete(Ability))
    session.commit()
    return session


def add_habit(session: Session, **fields) -> Habit:
    habit = Habit(**{"title": "Vyzkoušet jednu novou věc", "start_date": d(1), "log_mode": "note", **fields})
    session.add(habit)
    session.commit()
    session.refresh(habit)
    return habit


def put(client: TestClient, habit: Habit, day: dt.date, **body) -> dict:
    response = client.put(f"/api/habits/{habit.id}/days/{day.isoformat()}", json={"done": True, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_migration_switches_the_new_thing_habits_to_notes(session: Session) -> None:
    modes = {h.title: h.log_mode for h in session.exec(select(Habit)).all()}

    assert modes["Vyzkoušet jednu novou věc"] == "note"
    assert modes["Učit se novou dovednost"] == "note"
    assert modes["Ustlat postel"] == "check"


def test_ability_key_ignores_case_diacritics_and_spaces() -> None:
    assert ab.ability_key("  Lezení  na   stěně ") == ab.ability_key("lezeni na stene") == "lezeni na stene"


def test_entry_is_saved_and_a_bare_tick_keeps_it(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)
    day = today()

    saved = put(client, habit, day, note="  Lezecká stěna Lezec  ", ability="Lezení")
    assert saved["entry"]["note"] == "Lezecká stěna Lezec"
    assert saved["entry"]["ability"] == "Lezení"

    again = put(client, habit, day)  # a replay or the coach: fields left out stay
    assert again["entry"] == saved["entry"]
    assert len(empty.exec(select(HabitLog)).all()) == 1

    cleared = put(client, habit, day, note=None, ability=None)
    assert cleared["entry"] is None
    assert empty.exec(select(HabitLog)).one().ability_id is None


def test_ability_is_found_by_key_and_created_once(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty, frequency="weekly")
    put(client, habit, today(), ability="Lezení")
    put(client, habit, today() - dt.timedelta(days=1), ability="lezeni")
    put(client, habit, today() - dt.timedelta(days=1), ability="lezeni")  # replayed offline write

    abilities = empty.exec(select(Ability)).all()
    assert [a.name for a in abilities] == ["Lezení"]


def test_review_entry_with_stars_and_validation(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty, title="Nová restaurace", log_mode="review")
    url = f"/api/habits/{habit.id}/days/{today().isoformat()}"

    assert client.put(url, json={"done": True, "rating": 6}).status_code == 422
    assert client.put(url, json={"done": True, "note": "x" * 2001}).status_code == 422
    entry = put(client, habit, today(), rating=5, note="Skvělé ramen", ability="Japonská kuchyně")["entry"]
    assert (entry["rating"], entry["ability"]) == (5, "Japonská kuchyně")


def test_untick_deletes_the_entry(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)
    put(client, habit, today(), note="Bouldering", ability="Lezení")

    assert client.put(f"/api/habits/{habit.id}/days/{today()}", json={"done": False}).json()["entry"] is None
    assert empty.exec(select(HabitLog)).all() == []
    assert len(empty.exec(select(Ability)).all()) == 1  # the dovednost stays (0 entries)


def test_board_has_log_mode_entries_and_abilities(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty)
    plain = add_habit(empty, title="Ustlat postel", log_mode="check")
    put(client, habit, today(), note="Lezení venku", ability="Lezení")
    put(client, plain, today())

    board = client.get("/api/habits/board").json()
    by_title = {h["title"]: h for h in board["habits"]}

    assert by_title["Vyzkoušet jednu novou věc"]["log_mode"] == "note"
    assert by_title["Vyzkoušet jednu novou věc"]["entries"][today().isoformat()]["ability"] == "Lezení"
    assert by_title["Ustlat postel"]["entries"] == {}
    assert [a["name"] for a in board["abilities"]] == ["Lezení"]


def test_log_mode_on_create_and_update(client: TestClient, empty: Session) -> None:
    created = client.post("/api/habits", json={"title": "Nový recept", "log_mode": "review"}).json()
    assert created["log_mode"] == "review"
    assert client.post("/api/habits", json={"title": "x", "log_mode": "photo"}).status_code == 422

    updated = client.patch(f"/api/habits/{created['id']}", json={"log_mode": "note"}).json()
    assert updated["log_mode"] == "note"
    assert client.patch(f"/api/habits/{created['id']}", json={"log_mode": None}).json()["log_mode"] == "note"


def test_abilities_list_levels_rename_merge_delete(client: TestClient, empty: Session) -> None:
    habit = add_habit(empty, frequency="weekly")
    for back in range(3):
        put(client, habit, today() - dt.timedelta(days=back), ability="Lezení", note=f"stěna {back}")
    put(client, habit, today() - dt.timedelta(days=10), ability="Boulder")

    listed = client.get("/api/habits/abilities").json()
    assert [(a["name"], a["count"], a["level_name"], a["next_level_at"]) for a in listed] == [
        ("Lezení", 3, "Začátečník", 10),
        ("Boulder", 1, "Nováček", 3),
    ]
    climbing, boulder = listed
    assert climbing["last_note"] == "stěna 0"
    detail = client.get(f"/api/habits/abilities/{climbing['id']}").json()
    assert [e["note"] for e in detail["entries"]] == ["stěna 0", "stěna 1", "stěna 2"]

    assert client.patch(f"/api/habits/abilities/{boulder['id']}", json={"name": "LEZENÍ"}).status_code == 409
    renamed = client.patch(f"/api/habits/abilities/{boulder['id']}", json={"name": "Bouldering", "icon": "🧗"})
    assert renamed.json()["name"] == "Bouldering" and renamed.json()["icon"] == "🧗"

    merged = client.post(f"/api/habits/abilities/{boulder['id']}/merge", json={"into_id": climbing["id"]}).json()
    assert merged["count"] == 4
    assert client.get(f"/api/habits/abilities/{boulder['id']}").status_code == 404

    assert client.delete(f"/api/habits/abilities/{climbing['id']}").status_code == 204
    logs = empty.exec(select(HabitLog)).all()
    assert len(logs) == 4 and all(log.ability_id is None for log in logs)  # entries stay, without the link


def test_new_ability_pays_mind_once_also_on_paused_days(empty: Session) -> None:
    habit = add_habit(empty, frequency="weekly")
    for day, name in [(5, "Lezení"), (12, "lezeni"), (14, "Keramika")]:
        log = HabitLog(habit_id=habit.id, date=d(day), ability_id=ab.find_or_create(empty, name).id)
        empty.add(log)
    empty.add(RpgPause(start_date=d(13), end_date=d(15)))
    empty.commit()

    ledger = rpg.build_ledger(empty, d(16))
    new = [(e.date, e.amount, e.text) for e in ledger.entries if e.kind == "ability_new"]

    assert new == [(d(5), 25, "Nová dovednost: Lezení"), (d(14), 25, "Nová dovednost: Keramika")]
    assert ledger.skills["mind"].xp >= 50


def test_same_named_dovednost_completes_a_skill_bucket_item(empty: Session) -> None:
    from app.models.bucket import BucketItem
    from app.services import bucket as bk

    habit = add_habit(empty, frequency="weekly")
    empty.add(BucketItem(title="Lezení", category="skill", rarity=2))
    empty.add(BucketItem(title="Lezení", category="sport", rarity=2))  # other categories are left alone
    empty.commit()
    empty.add(HabitLog(habit_id=habit.id, date=today(), ability_id=ab.find_or_create(empty, "Lezení").id))
    empty.commit()

    states = {(s.item.category, s.item.title): s for s in bk.load(empty, today()).items}

    skill = states[("skill", "Lezení")]
    assert (skill.source, skill.done_on, skill.auto_label, skill.xp) == ("auto", today(), "Dovednost: Lezení", 150)
    assert states[("sport", "Lezení")].source is None


def test_resolve_for_the_coach(empty: Session) -> None:
    ab.find_or_create(empty, "Lezení")
    empty.commit()

    assert ab.resolve(empty, "LEZENI")[0].name == "Lezení"
    assert ab.resolve(empty, "Lezeni na skalach") == (None, ["Lezení"])
    assert ab.resolve(empty, "Keramika") == (None, [])


def coach_tools(session: Session) -> dict:
    from app.services.ai_tools import ToolContext, build_coach_tools

    now = dt.datetime(2026, 10, 18, 9, 0, tzinfo=dt.UTC)
    return {fn.__name__: fn for fn in build_coach_tools(ToolContext(session=session, now=now))}


def test_coach_saves_an_entry_and_asks_about_a_similar_dovednost(empty: Session) -> None:
    from google.genai import _extra_utils

    habit = add_habit(empty)
    ab.find_or_create(empty, "Lezení")
    empty.commit()
    tools = coach_tools(empty)
    args = {"habit_titles": [habit.title], "note": "Stěna Lezec", "rating": 5, "ability": "lezeni"}

    result = _extra_utils.invoke_function_from_dict_args(args, tools["set_habits_done"])
    assert result["entry_saved"] == {"note": "Stěna Lezec", "rating": 5, "ability": "Lezení"}

    similar = tools["set_habits_done"](habit_titles=[habit.title], date="2026-10-17", ability="Lezení na skalách")
    assert similar["ability_not_saved"] == {"input": "Lezení na skalách", "similar": ["Lezení"]}
    assert empty.get(HabitLog, (habit.id, d(17))).ability_id is None  # ticked, no dovednost
    forced = tools["set_habits_done"](
        habit_titles=[habit.title], date="2026-10-17", ability="Lezení na skalách", ability_is_new=True
    )
    assert forced["entry_saved"]["ability"] == "Lezení na skalách"
    assert "error" in tools["set_habits_done"](habit_titles=[habit.title, "x"], note="a")

    listed = tools["get_abilities"]()["abilities"]
    assert [(a["name"], a["times"]) for a in listed] == [("Lezení", 1), ("Lezení na skalách", 1)]
    assert listed[0]["latest"] == [{"date": "2026-10-18", "habit": habit.title, "note": "Stěna Lezec", "rating": 5}]


def test_weekly_ability_quest_when_mind_is_weakest(empty: Session) -> None:
    from app.services import quests as qs

    habit = add_habit(empty, frequency="weekly", start_date=d(1))
    gym = add_habit(empty, title="Posilovna", log_mode="check", skill="body", frequency="daily", start_date=d(1))
    for day in range(1, 26):
        empty.add(HabitLog(habit_id=gym.id, date=d(day)))
    empty.add(HabitLog(habit_id=habit.id, date=d(28), ability_id=ab.find_or_create(empty, "Keramika").id))
    empty.commit()

    ledger = rpg.build_ledger(empty, d(29))
    quest = next(q for q in ledger.quests if q.key == "ability")
    assert (quest.title, quest.done_on, quest.skill) == ("Vyzkoušej novou dovednost", d(28), "mind")
    assert any(e.kind == "quest" and e.text == "Výprava splněna: Vyzkoušej novou dovednost" for e in ledger.entries)

    board = hs.load_board(empty, end=d(29))
    history = qs.load_history(empty, d(1), d(29))
    before = qs.week_quests(history, board, d(19), d(25), {"mind": 0})
    assert all(q.key != "ability" for q in before)  # weeks before the feature keep their quests
