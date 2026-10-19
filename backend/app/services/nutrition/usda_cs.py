"""Czech names for the USDA seed and which of its foods are hidden (E28), from the agent's hand-made data files.

`app/data/usda_cs/*.tsv`: one USDA food per line, `<fdc_id><TAB><Czech name>`; the name `-` hides the food
(a duplicate or irrelevant variant: it stays a micronutrient reference, but is out of the food list and the
Czech search). Applied on every start (`app.seed`), idempotently: a Czech name is only set where none exists
yet (the user's own naming wins) and a food already eaten is never hidden.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "usda_cs"
HIDE = "-"


@dataclass
class CzechRows:
    names: dict[int, str]
    hidden: set[int]


def load(directory: Path = DATA_DIR) -> CzechRows:
    names: dict[int, str] = {}
    hidden: set[int] = set()
    for path in sorted(directory.glob("*.tsv")):
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            fdc, sep, name = line.partition("\t")
            if not sep or not fdc.strip().isdigit() or not name.strip():
                raise ValueError(f"{path.name}:{number}: expected '<fdc_id>\\t<name>', got {raw!r}")
            fdc_id, name = int(fdc), name.strip()
            if fdc_id in names or fdc_id in hidden:
                raise ValueError(f"{path.name}:{number}: fdc {fdc_id} listed twice")
            if name == HIDE:
                hidden.add(fdc_id)
            else:
                names[fdc_id] = name
    return CzechRows(names, hidden)


def apply(session: Session, rows: CzechRows | None = None) -> tuple[int, int]:
    """(foods named, foods hidden) by this run."""
    rows = rows or load()
    conn = session.connection()
    named = hidden = 0
    if rows.names:
        named = conn.execute(
            text(
                "UPDATE foods f SET name_cs = v.name FROM (SELECT unnest(CAST(:ids AS text[])) AS ext, "
                "unnest(CAST(:names AS text[])) AS name) v WHERE f.external_id = v.ext AND f.name_cs IS NULL"
            ),
            {"ids": [f"usda:{i}" for i in rows.names], "names": list(rows.names.values())},
        ).rowcount
    if rows.hidden:
        hidden = conn.execute(
            text(
                "UPDATE foods f SET hidden = true WHERE f.external_id = ANY(CAST(:ids AS text[])) AND NOT f.hidden "
                "AND NOT EXISTS (SELECT 1 FROM meal_log_items i WHERE i.food_id = f.id)"
            ),
            {"ids": [f"usda:{i}" for i in rows.hidden]},
        ).rowcount
    session.commit()
    return named, hidden


if __name__ == "__main__":
    from app.database import engine

    with Session(engine) as db:
        n, h = apply(db)
    print(f"usda cs: {n} named, {h} hidden")
