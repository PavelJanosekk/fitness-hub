"""bucket list

Bucket list tables (E36, docs/bucket-list-module-spec.md) and a one-time seed: the user's list sent on 2026-10-20,
cleaned up (Czech titles, typos, merged duplicates). Items marked done there are `done_before_app` (no date, no XP).
The 110 nearby day trips are not here: they belong to the side quests (D6). Seeded here and not in app.seed, so
items the user deletes never come back. Also adds the calisthenics exercises the auto rules point at.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-20 11:00:00
"""

import datetime as dt
import json
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SKILL_EXERCISES = [
    ("Muscle Up", "back"),
    ("L-Sit", "core"),
    ("Handstand", "shoulders"),
    ("Planche", "shoulders"),
]

DONE = True
OPEN = False
# (category, title, rarity 1-4, done before the app, extras)
SEED: list[tuple[str, str, int, bool, dict]] = [
    # Jídlo & pití
    ("food", "Dračí ovoce", 1, DONE, {}),
    ("food", "Pořádný steak", 1, DONE, {}),
    ("food", "Hmyz", 1, DONE, {}),
    ("food", "Ústřice", 1, DONE, {}),
    ("food", "Sushi", 1, DONE, {}),
    ("food", "Kimči", 1, DONE, {}),
    ("food", "Sépie", 1, DONE, {}),
    ("food", "Wasabi", 1, DONE, {}),
    ("food", "Klokaní maso", 1, DONE, {}),
    ("food", "Voda přímo z pramene", 1, DONE, {}),
    ("food", "Domácí sushi", 2, DONE, {}),
    ("food", "Topinambur", 1, DONE, {}),
    ("food", "Humr", 2, OPEN, {"cost": 3}),
    ("food", "Lanýže", 2, OPEN, {"cost": 3}),
    ("food", "Obsluha u stolu", 2, OPEN, {"cost": 3, "note": "Table side service"}),
    ("food", "Laverbread", 2, OPEN, {"note": "Velšská pochoutka z mořských řas", "country_codes": ["GB"]}),
    ("food", "Hovězí jazyk", 1, OPEN, {}),
    ("food", "Mořský ježek", 2, OPEN, {"cost": 2}),
    ("food", "Nové koření", 1, OPEN, {}),
    ("food", "Nové koktejly", 1, OPEN, {}),
    ("food", "Nejpálivější chilli", 2, OPEN, {}),
    ("food", "Chilli lízátko", 1, OPEN, {}),
    ("food", "Belgická čokoláda", 1, OPEN, {}),
    ("food", "Bubble tea", 1, OPEN, {}),
    ("food", "Bloody Mary", 1, OPEN, {}),
    ("food", "Guinness", 1, OPEN, {}),
    ("food", "Krocan jako na Díkůvzdání", 2, OPEN, {}),
    ("food", "Vlastní těstoviny", 1, OPEN, {}),
    ("food", "Uvařit vlastní pivo", 3, OPEN, {}),
    # Cestování (Země + Zahraničí - Nápady, merged)
    ("travel", "Itálie", 2, DONE, {"country_codes": ["IT"]}),
    ("travel", "Chorvatsko", 2, DONE, {"country_codes": ["HR"]}),
    ("travel", "Rusko", 2, DONE, {"country_codes": ["RU"]}),
    ("travel", "Asie", 3, DONE, {}),
    ("travel", "Japonsko", 3, DONE, {"country_codes": ["JP"]}),
    ("travel", "Španělsko", 2, DONE, {"country_codes": ["ES"]}),
    ("travel", "USA – národní parky", 4, OPEN, {"country_codes": ["US"], "cost": 3}),
    ("travel", "Havaj", 4, OPEN, {"country_codes": ["US"], "cost": 3}),
    ("travel", "Nový Zéland", 4, OPEN, {"country_codes": ["NZ"], "cost": 3}),
    ("travel", "Francie", 2, OPEN, {"country_codes": ["FR"], "cost": 2}),
    ("travel", "Vietnam", 3, OPEN, {"country_codes": ["VN"], "cost": 3}),
    ("travel", "Thajsko", 3, OPEN, {"country_codes": ["TH"], "cost": 3}),
    ("travel", "Švýcarsko", 2, OPEN, {"country_codes": ["CH"], "cost": 3}),
    ("travel", "Kyrgyzstán + Uzbekistán", 3, OPEN, {"country_codes": ["KG", "UZ"], "cost": 2}),
    ("travel", "Island", 3, OPEN, {"country_codes": ["IS"], "cost": 3}),
    ("travel", "Čína", 3, OPEN, {"country_codes": ["CN"], "cost": 3}),
    ("travel", "Indonésie (Bali)", 3, OPEN, {"country_codes": ["ID"], "cost": 3}),
    ("travel", "Albánie", 2, OPEN, {"country_codes": ["AL"], "cost": 1}),
    ("travel", "Jižní Korea", 3, OPEN, {"country_codes": ["KR"], "cost": 3}),
    ("travel", "Azory", 3, OPEN, {"country_codes": ["PT"], "cost": 2}),
    ("travel", "Kanada", 3, OPEN, {"country_codes": ["CA"], "cost": 3}),
    ("travel", "Skotsko (Edinburgh i příroda)", 2, OPEN, {"country_codes": ["GB"], "cost": 2}),
    ("travel", "Filipíny", 3, OPEN, {"country_codes": ["PH"], "cost": 3}),
    ("travel", "Skandinávie (Švédsko / Norsko / Finsko)", 3, OPEN, {"country_codes": ["SE", "NO", "FI"], "cost": 3}),
    ("travel", "Málaga", 2, OPEN, {"country_codes": ["ES"], "cost": 1, "note": "levně"}),
    ("travel", "Peru", 4, OPEN, {"country_codes": ["PE"], "cost": 3}),
    ("travel", "Jordánsko", 3, OPEN, {"country_codes": ["JO"], "cost": 2}),
    ("travel", "Sicílie", 2, OPEN, {"country_codes": ["IT"], "cost": 2}),
    # Výpravy (Cestovat okolí + Zahraničí + mountains from Místa, merged)
    ("expedition", "Praděd", 1, DONE, {"country_codes": ["CZ"], "lat": 50.0833, "lon": 17.2311}),
    ("expedition", "Dolní Morava", 1, DONE, {"country_codes": ["CZ"], "lat": 50.1219, "lon": 16.7994}),
    (
        "expedition",
        "Jizerské hory",
        2,
        OPEN,
        {"travel_time": "3 h 2 min", "country_codes": ["CZ"], "lat": 50.82, "lon": 15.25},
    ),
    (
        "expedition",
        "České Švýcarsko – Pravčická brána",
        2,
        OPEN,
        {"travel_time": "3 h 55 min", "country_codes": ["CZ"], "lat": 50.8839, "lon": 14.2808},
    ),
    (
        "expedition",
        "Sněžka",
        2,
        OPEN,
        {"travel_time": "2 h 30 min", "country_codes": ["CZ"], "lat": 50.736, "lon": 15.7399},
    ),
    (
        "expedition",
        "Ještěd",
        1,
        OPEN,
        {"travel_time": "3 h 15 min", "country_codes": ["CZ"], "lat": 50.7325, "lon": 14.9847},
    ),
    (
        "expedition",
        "Prachovské skály",
        1,
        OPEN,
        {"travel_time": "2 h 30 min", "country_codes": ["CZ"], "lat": 50.4703, "lon": 15.2847},
    ),
    (
        "expedition",
        "Šumava – Bílá strž (vodopády)",
        2,
        OPEN,
        {"travel_time": "4 h 22 min", "country_codes": ["CZ"], "lat": 49.136, "lon": 13.186, "season": "summer"},
    ),
    ("expedition", "Beskid Żywiecki", 2, OPEN, {"country_codes": ["PL"], "lat": 49.5731, "lon": 19.5294}),
    (
        "expedition",
        "Achensee",
        2,
        OPEN,
        {"travel_time": "6 h 18 min", "country_codes": ["AT"], "lat": 47.45, "lon": 11.71, "season": "summer"},
    ),
    (
        "expedition",
        "Orlí hnízdo",
        2,
        OPEN,
        {"travel_time": "5 h 4 min", "country_codes": ["DE"], "lat": 47.611, "lon": 13.0418},
    ),
    (
        "expedition",
        "Wolfgangsee",
        2,
        OPEN,
        {"travel_time": "4 h 40 min", "country_codes": ["AT"], "lat": 47.74, "lon": 13.42, "season": "summer"},
    ),
    (
        "expedition",
        "Hochschwab",
        3,
        OPEN,
        {"travel_time": "4 h", "country_codes": ["AT"], "lat": 47.6175, "lon": 15.143, "season": "summer"},
    ),
    (
        "expedition",
        "Pieniny",
        2,
        OPEN,
        {"travel_time": "5 h", "country_codes": ["PL", "SK"], "lat": 49.4167, "lon": 20.4167},
    ),
    ("expedition", "Tatry", 3, OPEN, {"country_codes": ["SK"], "lat": 49.1194, "lon": 20.0628, "season": "summer"}),
    ("expedition", "Kaprun", 2, OPEN, {"travel_time": "6 h", "country_codes": ["AT"], "lat": 47.27, "lon": 12.76}),
    ("expedition", "Attersee", 2, OPEN, {"country_codes": ["AT"], "lat": 47.87, "lon": 13.53, "season": "summer"}),
    (
        "expedition",
        "Přechod Dolomit",
        4,
        OPEN,
        {"country_codes": ["IT"], "lat": 46.5, "lon": 11.85, "season": "summer", "cost": 2},
    ),
    # Zážitky
    ("experience", "Dovolená v zahraničí", 1, DONE, {}),
    ("experience", "Akvárium", 1, DONE, {}),
    ("experience", "Plavat s medúzami", 2, DONE, {}),
    ("experience", "Spát v týpí", 1, DONE, {}),
    ("experience", "Plavat pod vodopádem", 2, DONE, {}),
    ("experience", "Výlet s přáteli", 2, DONE, {"note": "friendcation"}),
    ("experience", "Divadlo", 1, DONE, {}),
    ("experience", "Koupání nahý", 1, DONE, {}),
    ("experience", "Geocaching", 1, DONE, {}),
    ("experience", "Plavba lodí", 3, OPEN, {"cost": 3, "note": "cruise"}),
    ("experience", "Safari", 4, OPEN, {"cost": 3}),
    ("experience", "Deštný prales", 3, OPEN, {"cost": 3}),
    ("experience", "Havajská luau", 2, OPEN, {"country_codes": ["US"]}),
    ("experience", "Spát na hausbótu", 2, OPEN, {"cost": 2}),
    (
        "experience",
        "Navštívit všech 7 kontinentů",
        4,
        OPEN,
        {"auto_rule": "continents", "auto_threshold": 7, "cost": 3},
    ),
    ("experience", "Motýlí farma", 1, OPEN, {}),
    ("experience", "Mayské ruiny", 4, OPEN, {"country_codes": ["MX"], "cost": 3}),
    ("experience", "Pyramidy", 4, OPEN, {"country_codes": ["EG"], "cost": 2}),
    ("experience", "Let balónem", 3, OPEN, {"cost": 3}),
    ("experience", "Muzikál", 1, OPEN, {"cost": 2}),
    ("experience", "Koncert oblíbené kapely", 2, OPEN, {"cost": 2}),
    ("experience", "Jízda limuzínou", 1, OPEN, {"cost": 2}),
    ("experience", "Laser game", 1, OPEN, {"cost": 1}),
    # Adrenalin
    ("adrenaline", "Čtyřkolka", 1, DONE, {}),
    ("adrenaline", "Paintball", 1, DONE, {}),
    ("adrenaline", "Seskok padákem", 3, OPEN, {"cost": 3}),
    ("adrenaline", "Bungee jumping", 3, OPEN, {"cost": 2}),
    ("adrenaline", "Potápění s přístrojem", 3, OPEN, {"cost": 3}),
    ("adrenaline", "Rogalo", 3, OPEN, {"cost": 3}),
    ("adrenaline", "Zipline", 1, OPEN, {"cost": 1}),
    ("adrenaline", "Mechanický býk", 1, OPEN, {"cost": 1}),
    ("adrenaline", "Řídit motorku", 2, OPEN, {"cost": 2}),
    ("adrenaline", "Řídit sporťák", 2, OPEN, {"cost": 3}),
    # Sport & pohyb
    ("sport", "Kajak", 1, DONE, {}),
    ("sport", "Six pack", 3, DONE, {}),
    ("sport", "Uběhnout maraton", 4, OPEN, {"auto_rule": "marathon", "planned_for": dt.date(2027, 5, 2)}),
    ("sport", "Snowboard", 2, OPEN, {"season": "winter", "cost": 2}),
    ("sport", "Squash", 1, OPEN, {"cost": 1}),
    ("sport", "Surfování", 2, OPEN, {"season": "summer", "cost": 3}),
    ("sport", "Jízda na koni", 1, OPEN, {"cost": 1}),
    (
        "sport",
        "Vylézt na horu",
        2,
        OPEN,
        {"auto_rule": "hike", "auto_threshold": 1000, "note": "túra s převýšením 1 000 m"},
    ),
    ("sport", "Lezecká stěna", 1, OPEN, {"cost": 1}),
    # Dovednosti
    ("skill", "Muscle up", 3, DONE, {"auto_exercise": "Muscle Up"}),
    ("skill", "Kalistenika", 3, OPEN, {}),
    ("skill", "L-sit", 2, OPEN, {"auto_exercise": "L-Sit"}),
    ("skill", "Stojka", 3, OPEN, {"auto_exercise": "Handstand"}),
    ("skill", "Planche", 4, OPEN, {"auto_exercise": "Planche"}),
    ("skill", "Naučit se šachy", 2, OPEN, {}),
    ("skill", "Naučit se rusky", 4, OPEN, {"steps": ["Azbuka", "A1", "A2", "B1"]}),
    # Tělo & mysl
    ("wellbeing", "Solárko", 1, OPEN, {"cost": 1}),
    ("wellbeing", "Masáž", 1, OPEN, {"cost": 1}),
    ("wellbeing", "Reiki", 1, OPEN, {"cost": 1}),
    ("wellbeing", "Akupunktura", 1, OPEN, {"cost": 1}),
    ("wellbeing", "Týden vegetariánem", 2, OPEN, {}),
    ("wellbeing", "Týden veganem", 2, OPEN, {}),
    ("wellbeing", "Dobrovolnictví", 2, OPEN, {}),
    ("wellbeing", "Překonat celoživotní strach", 3, OPEN, {}),
]


def upgrade() -> None:
    op.create_table(
        "bucket_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rarity", sa.Integer(), nullable=False),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("link", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("travel_time", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("season", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("cost", sa.Integer(), nullable=True),
        sa.Column("planned_for", sa.Date(), nullable=True),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("done_before_app", sa.Boolean(), nullable=False),
        sa.Column("memory", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("year_goal", sa.Integer(), nullable=True),
        sa.Column("auto_rule", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("auto_exercise_id", sa.Integer(), nullable=True),
        sa.Column("auto_threshold", sa.Float(), nullable=True),
        sa.Column("country_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "auto_rule IS NULL OR auto_rule IN ('marathon', 'exercise', 'hike', 'continents')",
            name=op.f("ck_bucket_items_auto_rule"),
        ),
        sa.CheckConstraint(
            "category IS NULL OR category IN ('travel', 'expedition', 'experience', 'adrenaline', 'sport', 'skill',"
            " 'food', 'wellbeing')",
            name=op.f("ck_bucket_items_category"),
        ),
        sa.CheckConstraint("season IS NULL OR season IN ('summer', 'winter')", name=op.f("ck_bucket_items_season")),
        sa.CheckConstraint("rarity BETWEEN 1 AND 4", name=op.f("ck_bucket_items_rarity_range")),
        sa.CheckConstraint("cost IS NULL OR cost BETWEEN 1 AND 3", name=op.f("ck_bucket_items_cost_range")),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_bucket_items_rating_range")),
        sa.ForeignKeyConstraint(
            ["auto_exercise_id"],
            ["exercises.id"],
            name=op.f("fk_bucket_items_auto_exercise_id_exercises"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bucket_items")),
    )
    op.create_table(
        "bucket_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["item_id"], ["bucket_items.id"], name=op.f("fk_bucket_steps_item_id_bucket_items"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bucket_steps")),
    )
    op.create_index(op.f("ix_bucket_steps_item_id"), "bucket_steps", ["item_id"], unique=False)
    op.create_table(
        "visited_countries",
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=2), nullable=False),
        sa.Column("visited_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_visited_countries")),
    )
    _seed()


def _seed() -> None:
    bind = op.get_bind()
    exercise_ids = {}
    for name, group in SKILL_EXERCISES:
        bind.execute(
            sa.text(
                "INSERT INTO exercises (name, muscle_group, equipment) VALUES (:name, :group, 'bodyweight')"
                " ON CONFLICT (name) DO NOTHING"
            ),
            {"name": name, "group": group},
        )
        exercise_ids[name] = bind.execute(
            sa.text("SELECT id FROM exercises WHERE name = :name"), {"name": name}
        ).scalar_one()
    for category, title, rarity, done, extras in SEED:
        extras = dict(extras)
        steps = extras.pop("steps", [])
        if exercise := extras.pop("auto_exercise", None):
            extras |= {"auto_rule": "exercise", "auto_exercise_id": exercise_ids[exercise]}
        columns = {
            "title": title,
            "category": category,
            "rarity": rarity,
            "done_before_app": done,
            **extras,
            "country_codes": json.dumps(extras.get("country_codes", [])),
        }
        names = ", ".join(columns)
        values = ", ".join(
            "CAST(:country_codes AS jsonb)" if name == "country_codes" else f":{name}" for name in columns
        )
        item_id = bind.execute(
            sa.text(f"INSERT INTO bucket_items ({names}, created_at) VALUES ({values}, now()) RETURNING id"), columns
        ).scalar_one()
        for position, step in enumerate(steps):
            bind.execute(
                sa.text("INSERT INTO bucket_steps (item_id, position, title) VALUES (:item_id, :position, :title)"),
                {"item_id": item_id, "position": position, "title": step},
            )
    # Home counts on the world map
    bind.execute(sa.text("INSERT INTO visited_countries (code, created_at) VALUES ('CZ', now())"))


def downgrade() -> None:
    op.drop_table("visited_countries")
    op.drop_index(op.f("ix_bucket_steps_item_id"), table_name="bucket_steps")
    op.drop_table("bucket_steps")
    op.drop_table("bucket_items")
    # The calisthenics exercises stay: app.seed lists them too and sets may reference them
