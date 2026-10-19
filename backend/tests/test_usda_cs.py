"""Czech names and hidden duplicates for the USDA seed (E28): the loader, its rules, and the data files themselves."""

import datetime as dt
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.nutrition import Food, FoodSource, MealLog, MealLogItem
from app.services.nutrition import usda_cs
from app.services.nutrition.resolver import normalize


def usda(session: Session, fdc: int, name_en: str, name_cs: str | None = None) -> Food:
    row = Food(
        source=FoodSource.usda,
        external_id=f"usda:{fdc}",
        name_en=name_en,
        name_cs=name_cs,
        kcal=100,
        protein_g=10,
        carbs_g=10,
        fat_g=2,
    )
    session.add(row)
    session.commit()
    return row


def test_load_rejects_bad_lines_and_repeats(tmp_path: Path) -> None:
    (tmp_path / "a.tsv").write_text("# comment\n1\tKuřecí prsa, syrová\n2\t-\n", encoding="utf-8")
    rows = usda_cs.load(tmp_path)
    assert (rows.names, rows.hidden) == ({1: "Kuřecí prsa, syrová"}, {2})

    (tmp_path / "b.tsv").write_text("1\tZnovu\n", encoding="utf-8")
    with pytest.raises(ValueError, match="listed twice"):
        usda_cs.load(tmp_path)
    (tmp_path / "b.tsv").write_text("abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"b\.tsv:1"):
        usda_cs.load(tmp_path)


def test_apply_names_hides_and_respects_the_user(client: TestClient, session: Session) -> None:
    breast = usda(session, 171077, "Chicken, breast, raw")
    named = usda(session, 170379, "Broccoli, raw", name_cs="Brokolice moje")
    salted = usda(session, 168510, "Broccoli, cooked, with salt")
    eaten = usda(session, 169975, "Cabbage, raw")
    meal = MealLog(id=uuid.uuid4(), logged_date=dt.date(2026, 10, 1))
    session.add(meal)
    session.add(MealLogItem(meal_log_id=meal.id, label="Zelí", food_id=eaten.id, amount_g=100))
    session.commit()
    rows = usda_cs.CzechRows(
        names={171077: "Kuřecí prsa, syrová", 170379: "Brokolice, syrová"}, hidden={168510, 169975}
    )

    assert usda_cs.apply(session, rows) == (1, 1)
    assert usda_cs.apply(session, rows) == (0, 0)  # idempotent
    for food in (breast, named, salted, eaten):
        session.refresh(food)
    assert (breast.name_cs, named.name_cs) == ("Kuřecí prsa, syrová", "Brokolice moje")
    assert (salted.hidden, eaten.hidden) == (True, False)

    listed = {f["name"] for f in client.get("/api/nutrition/foods").json()}
    assert {"Kuřecí prsa, syrová", "Brokolice moje", "Zelí"} - listed == {"Zelí"}  # eaten food keeps its USDA name
    assert "Broccoli, cooked, with salt" not in {
        f["name"] for f in client.get("/api/nutrition/foods?q=broccoli").json()
    }
    assert [f["id"] for f in client.get("/api/nutrition/foods?hidden=true").json()] == [salted.id]
    unhidden = client.patch(f"/api/nutrition/foods/{salted.id}", json={"hidden": False}).json()
    assert unhidden["hidden"] is False


def test_data_files_have_no_duplicate_visible_names() -> None:
    """The user's rule (E28): one visible food per name, so no "4x chicken breast"."""
    rows = usda_cs.load()
    seen: dict[str, int] = {}
    duplicates = []
    for fdc, name in rows.names.items():
        key = normalize(name)
        if key in seen:
            duplicates.append(f"{name} ({seen[key]}, {fdc})")
        seen[key] = fdc
    assert duplicates == []
