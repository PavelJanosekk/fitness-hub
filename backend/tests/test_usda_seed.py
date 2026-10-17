"""USDA bulk seed (E3) against a tiny archive in USDA's CSV layout."""

import csv
import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, select

from app.models.nutrition import Food, FoodPortion
from app.services.nutrition.usda import Dataset, UsdaError, download, import_foods, parse, seed_usda

TABLES = {
    "food_category": [("id", "code", "description"), ("1", "0100", "Dairy and Egg Products"), ("2", "0500", "Poultry")],
    "food": [
        ("fdc_id", "data_type", "description", "food_category_id", "publication_date"),
        ("100", "foundation_food", "Egg, whole, raw, fresh", "1", "2019-04-01"),
        ("101", "foundation_food", "Chicken, breast, meat only, cooked, roasted", "2", "2019-04-01"),
        ("102", "foundation_food", "Mystery powder", "1", "2019-04-01"),  # no fat value → skipped
        ("900", "sub_sample_food", "Egg sample 7", "1", "2019-04-01"),  # other data type → ignored
    ],
    "food_nutrient": [
        ("id", "fdc_id", "nutrient_id", "amount", "data_points", "derivation_id", "min", "max", "median"),
        ("1", "100", "2047", "143", "", "", "", "", ""),
        ("2", "100", "1003", "12.56", "", "", "", "", ""),
        ("3", "100", "1004", "9.51", "", "", "", "", ""),
        ("4", "100", "1005", "0.72", "", "", "", "", ""),
        ("5", "100", "1093", "142", "", "", "", "", ""),
        ("6", "100", "9999", "1", "", "", "", "", ""),  # not a mapped nutrient
        ("7", "101", "1008", "165", "", "", "", "", ""),
        ("8", "101", "1003", "31", "", "", "", "", ""),
        ("9", "101", "1004", "3.6", "", "", "", "", ""),
        ("10", "101", "1005", "0", "", "", "", "", ""),
        ("11", "102", "1008", "400", "", "", "", "", ""),
        ("12", "102", "1003", "10", "", "", "", "", ""),
        ("13", "102", "1005", "80", "", "", "", "", ""),
        ("14", "900", "1008", "999", "", "", "", "", ""),
    ],
    "measure_unit": [("id", "name"), ("1000", "cup"), ("9999", "undetermined")],
    "food_portion": [
        ("id", "fdc_id", "seq_num", "amount", "measure_unit_id", "portion_description", "modifier", "gram_weight"),
        ("1", "100", "1", "1", "9999", "", "large", "50"),
        ("2", "100", "2", "1", "1000", "", "", "243"),
        ("3", "100", "3", "1", "9999", "", "broken", "0"),  # no weight → ignored
    ],
}


def make_zip(path: Path, tables: dict = TABLES) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, rows in tables.items():
            out = io.StringIO()
            csv.writer(out, quoting=csv.QUOTE_ALL).writerows(rows)
            archive.writestr(f"FoodData_test/{name}.csv", out.getvalue())
    return path


def foods_by_name(session: Session) -> dict[str, Food]:
    return {f.name_en: f for f in session.exec(select(Food)) if f.name_en}


def test_parse_keeps_only_the_data_type_and_mapped_nutrients(tmp_path: Path) -> None:
    foods = {f.fdc_id: f for f in parse(make_zip(tmp_path / "t.zip"), "foundation_food")}

    assert set(foods) == {"100", "101", "102"}
    assert foods["100"].category == "Dairy and Egg Products"
    assert 9999 not in foods["100"].amounts
    assert foods["100"].portions == {"1 large": 50.0, "1 cup": 243.0}


def test_import_maps_values_skips_incomplete_foods_and_is_idempotent(tmp_path: Path, session: Session) -> None:
    parsed = parse(make_zip(tmp_path / "t.zip"), "foundation_food")

    first = import_foods(session, parsed)
    egg = foods_by_name(session)["Egg, whole, raw, fresh"]
    egg.name_cs = "Vejce, celé, syrové"  # set later by the resolver; a re-seed must keep it
    session.add(egg)
    session.commit()
    second = import_foods(session, parsed)
    session.commit()

    foods = foods_by_name(session)
    egg, chicken = foods["Egg, whole, raw, fresh"], foods["Chicken, breast, meat only, cooked, roasted"]
    assert (first.foods, first.skipped, first.portions) == (2, 1, 2)
    assert (second.foods, second.portions) == (2, 2)
    assert len(foods) == 2
    assert (egg.external_id, egg.source, egg.kcal, egg.salt_g, egg.fiber_g) == ("usda:100", "usda", 143, 0.355, None)
    assert egg.micronutrients == {"sodium_mg": 142}
    assert egg.name_cs == "Vejce, celé, syrové"
    assert (egg.is_raw, chicken.is_raw) == (True, False)
    assert len(session.exec(select(FoodPortion).where(FoodPortion.food_id == egg.id)).all()) == 2


def test_download_verifies_the_checksum(tmp_path: Path) -> None:
    payload = make_zip(tmp_path / "src.zip").read_bytes()
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)))
    good = Dataset("x.zip", hashlib.sha256(payload).hexdigest(), "foundation_food")
    (tmp_path / "dl").mkdir()

    assert download(http, good, tmp_path / "dl").read_bytes() == payload
    with pytest.raises(UsdaError, match="sha256"):
        download(http, Dataset("x.zip", "0" * 64, "foundation_food"), tmp_path / "dl")


def test_seed_runs_every_dataset(tmp_path: Path, session: Session) -> None:
    payload = make_zip(tmp_path / "src.zip").read_bytes()
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)))
    dataset = Dataset("x.zip", hashlib.sha256(payload).hexdigest(), "foundation_food")

    result = seed_usda(session, http, (dataset,))

    assert (result.foods, result.skipped) == (2, 1)
