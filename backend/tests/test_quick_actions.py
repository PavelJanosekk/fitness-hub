"""Quick actions on Jídlo (E42): upsert with items, list with totals, idempotent logging, delete."""

import datetime as dt
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.nutrition import Food, FoodSource

D = dt.date(2026, 10, 10)


def food(session: Session, name: str, kcal: float, protein_g: float) -> Food:
    row = Food(source=FoodSource.custom, name_cs=name, kcal=kcal, protein_g=protein_g, carbs_g=50.0, fat_g=5.0)
    session.add(row)
    session.commit()
    return row


def oats_with_whey(session: Session) -> dict:
    oats, whey = food(session, "ovesné vločky", 400, 13), food(session, "whey", 380, 75)
    return {
        "name": "Vločky s proteinem",
        "emoji": "🥣",
        "color": "amber",
        "meal_type": "breakfast",
        "start_minute": 300,
        "end_minute": 660,
        "items": [{"food_id": oats.id, "amount_g": 50}, {"food_id": whey.id, "amount_g": 30}],
    }


def test_upsert_lists_items_and_totals(client: TestClient, session: Session) -> None:
    body = oats_with_whey(session)
    action_id = uuid.uuid4()
    saved = client.put(f"/api/nutrition/quick-actions/{action_id}", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["kcal"] == 200 + 114
    assert saved.json()["protein_g"] == 6.5 + 22.5

    # A second PUT edits in place and replaces the items
    body |= {"name": "Jen vločky", "items": body["items"][:1]}
    client.put(f"/api/nutrition/quick-actions/{action_id}", json=body)
    [listed] = client.get("/api/nutrition/quick-actions").json()
    assert listed["name"] == "Jen vločky"
    assert [i["food_name"] for i in listed["items"]] == ["ovesné vločky"]


def test_upsert_rejects_bad_windows_and_unknown_foods(client: TestClient, session: Session) -> None:
    body = oats_with_whey(session)
    url = f"/api/nutrition/quick-actions/{uuid.uuid4()}"
    assert client.put(url, json=body | {"start_minute": 700}).status_code == 422
    assert client.put(url, json=body | {"items": [{"food_id": 999_999, "amount_g": 10}]}).status_code == 422
    assert client.put(url, json=body | {"color": "pink"}).status_code == 422
    assert client.get("/api/nutrition/quick-actions").json() == []


def test_log_is_idempotent_and_joins_the_meal(client: TestClient, session: Session) -> None:
    action_id = uuid.uuid4()
    client.put(f"/api/nutrition/quick-actions/{action_id}", json=oats_with_whey(session))
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    url = f"/api/nutrition/quick-actions/{action_id}/log"

    logged = client.post(url, json={"date": D.isoformat(), "item_ids": ids})
    assert logged.status_code == 200, logged.text
    assert [i["id"] for i in logged.json()] == ids
    assert client.post(url, json={"date": D.isoformat(), "item_ids": ids}).status_code == 200  # a retry

    [meal] = client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()["meals"]
    assert meal["meal_type"] == "breakfast"
    assert [(i["food_name"], i["amount_g"]) for i in meal["items"]] == [("ovesné vločky", 50), ("whey", 30)]
    assert client.post(url, json={"date": D.isoformat(), "item_ids": ids[:1]}).status_code == 422


def test_delete_keeps_logged_items_and_foods_in_actions_stay(client: TestClient, session: Session) -> None:
    body = oats_with_whey(session)
    action_id = uuid.uuid4()
    client.put(f"/api/nutrition/quick-actions/{action_id}", json=body)

    # A food used in an action can't be deleted
    assert client.delete(f"/api/nutrition/foods/{body['items'][0]['food_id']}").status_code == 409

    client.post(
        f"/api/nutrition/quick-actions/{action_id}/log",
        json={"date": D.isoformat(), "item_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
    )
    assert client.delete(f"/api/nutrition/quick-actions/{action_id}").status_code == 204
    assert client.get("/api/nutrition/quick-actions").json() == []
    assert len(client.get("/api/nutrition/day", params={"date": D.isoformat()}).json()["meals"][0]["items"]) == 2
    assert (
        client.post(f"/api/nutrition/quick-actions/{action_id}/log", json={"item_ids": [str(uuid.uuid4())]}).status_code
        == 404
    )


def test_logged_items_carry_the_action_until_it_is_deleted(client: TestClient, session: Session) -> None:
    action_id = uuid.uuid4()
    client.put(f"/api/nutrition/quick-actions/{action_id}", json=oats_with_whey(session))
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    logged = client.post(f"/api/nutrition/quick-actions/{action_id}/log", json={"date": D.isoformat(), "item_ids": ids})
    assert {i["quick_action_id"] for i in logged.json()} == {str(action_id)}

    [meal] = client.get("/api/nutrition/summary", params={"date": D.isoformat()}).json()["meals"]
    assert {i["quick_action_id"] for i in meal["items"]} == {str(action_id)}

    # Gram edits keep the mark; deleting the action leaves the eaten items unmarked
    client.put(
        f"/api/nutrition/items/{ids[0]}",
        json={"food_id": meal["items"][0]["food_id"], "amount_g": 60, "meal_type": "breakfast"},
    )
    client.delete(f"/api/nutrition/quick-actions/{action_id}")
    session.expire_all()
    [meal] = client.get("/api/nutrition/summary", params={"date": D.isoformat()}).json()["meals"]
    assert sorted((i["amount_g"], i["quick_action_id"]) for i in meal["items"]) == [(30, None), (60, None)]
