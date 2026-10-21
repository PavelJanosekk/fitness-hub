"""side quests

Side quests table (E45, docs/side-quests-module-spec.md) and a one-time seed of the 100 nearby day trips from the
user's list of 2026-10-20 (*Výlety - Tipy*): Czech titles with diacritics, five pairs merged (95 rows), drive time
and distance from home. The user's own side quests are seeded later. Seeded here and not in app.seed, so quests
the user deletes never come back.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-21 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (title, drive minutes, km)
TRIPS: list[tuple[str, int, int]] = [
    ("Macocha a Punkevní jeskyně", 25, 20),
    ("Rudické propadání", 20, 18),
    ("Pustý žleb (Skalní mlýn)", 25, 22),
    ("Suchý žleb", 25, 22),
    ("Hřebenáč u Sloupu", 25, 22),
    ("Sloupsko-šošůvské jeskyně", 25, 22),
    ("Vodopády Bílé vody (Habrůvka)", 30, 25),
    ("Bořinovský vodopád", 15, 10),
    ("Kaplička sv. Otýlie (Boskovice)", 10, 5),
    ("Boskovický žleb", 5, 2),
    ("Údolí Svratky a přehrada Vír", 50, 40),
    ("Květnice (Tišnov)", 60, 55),
    ("Pernštejnský okruh", 55, 45),
    ("Údolí Doubravy (Bílek)", 100, 90),
    ("Krásensko – údolí Rakovce", 35, 30),
    ("Údolí Křetínky", 20, 15),
    ("Velký Chlum (Letovice)", 15, 12),
    ("Rozhledna Karasín", 50, 40),
    ("Rozhledna Babylon (Kozárov)", 35, 30),
    ("Horní les (Veselka)", 30, 25),
    ("Rozhledna Zlobice", 60, 55),
    ("Devět skal (Žďárské vrchy)", 90, 75),
    ("Drátník (Žďárské vrchy)", 90, 80),
    ("Pasecká skála", 80, 70),
    ("Obora Doubravice", 10, 8),
    ("Bukovinka – krasový okruh", 35, 30),
    ("Habrůvecká bučina", 30, 25),
    ("Josefovské údolí", 30, 25),
    ("Kateřinská jeskyně", 30, 25),
    ("Stará huť u Adamova", 35, 28),
    ("Zámek Lysice a park", 15, 12),
    ("Rájecké rybníky", 15, 12),
    ("Boskovice – hrad a zámek", 5, 2),
    ("Hrad Pernštejn", 55, 45),
    ("Hrad Bouzov", 60, 55),
    ("Hrad Veveří", 80, 70),
    ("Zámek Rájec nad Svitavou", 10, 8),
    ("Hrad Cimburk (Koryčany)", 100, 90),
    ("Zřícenina Holštejn", 25, 20),
    ("Zřícenina Obřany", 70, 60),
    ("Bazilika Křtiny", 30, 25),
    ("Adršpašské skály", 150, 150),
    ("Teplické skály", 150, 155),
    ("Rozhledna Kralický háj (Prostějov)", 50, 45),
    ("Plumlov – přehrada a zámek", 55, 50),
    ("Javoříčské jeskyně", 70, 65),
    ("Mladečské jeskyně", 70, 70),
    ("Svatý Kopeček (Olomouc)", 75, 75),
    ("Rozhledna Velký Kosíř", 60, 55),
    ("Hrad Helfštýn", 90, 95),
    ("Zřícenina Lukov", 100, 110),
    ("Svatý Hostýn (Hostýnské vrchy)", 100, 110),
    ("Velký Javorník (Beskydy)", 140, 160),
    ("Pulčínské skály (Hradisko)", 120, 140),
    ("Vizovické vrchy", 110, 130),
    ("Chřiby – hrad Buchlov", 90, 100),
    ("Brněnská přehrada", 75, 65),
    ("Holedná – obora a rozhledna", 60, 55),
    ("Kamenný vrch (Kohoutovice)", 60, 55),
    ("Hády – vyhlídka", 60, 50),
    ("Stránská skála (Brno)", 60, 50),
    ("Rozhledna Akátová věž (Bílovice)", 50, 40),
    ("Zřícenina Lelekovice", 60, 50),
    ("Hrad Doubravník", 50, 45),
    ("Tři Studně (Vysočina)", 90, 75),
    ("Rybník Sykovec", 90, 75),
    ("Nové Mlýny (Vysočina)", 80, 70),
    ("CHKO Žďárské vrchy", 90, 75),
    ("Zelená hora (Žďár nad Sázavou)", 100, 85),
    ("Vyhlídka Kobyla (přehrada Vír)", 55, 45),
    ("Štěpánovský tunel", 60, 55),
    ("Skalní svět (Sloup)", 25, 22),
    ("Propast Macocha – horní můstek", 25, 20),
    ("Vilémovická lípa", 25, 22),
    ("Jeskyně Balcarka", 30, 25),
    ("Ochozská jeskyně", 40, 35),
    ("Hádecká jeskyně", 60, 50),
    ("Rozhledna Podvrší (Veselice)", 30, 25),
    ("Rozhledna Bukovec", 60, 50),
    ("Rozhledna Kelčský Javorník", 120, 140),
    ("Rozhledna Macecha (Lesná)", 30, 25),
    ("Vyhlídka Cikánský komín (Pernštejn)", 60, 50),
    ("Letovická přehrada", 15, 12),
    ("Klamovka (Olešnice)", 35, 28),
    ("Hrad Svojanov", 45, 40),
    ("Polička – hradby", 70, 60),
    ("Toulovcovy maštale", 80, 75),
    ("Rozhledna Terezka (Proseč)", 80, 80),
    ("Vodopády Bohdalov – Hartmanice", 75, 70),
    ("Hrad Lipnice nad Sázavou", 110, 110),
    ("Hrad Roštejn", 100, 100),
    ("Telč (UNESCO)", 110, 115),
    ("Mohelenská hadcová step", 90, 95),
    ("Zřícenina Templštejn", 90, 100),
    ("Meandry Rokytné", 90, 100),
]


def upgrade() -> None:
    op.create_table(
        "side_quests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("duration", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("link", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("travel_minutes", sa.Integer(), nullable=True),
        sa.Column("distance_km", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("done_before_app", sa.Boolean(), nullable=False),
        sa.Column("memory", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IS NULL OR category IN ('learn', 'make', 'food', 'activity', 'trip')",
            name=op.f("ck_side_quests_category"),
        ),
        sa.CheckConstraint(
            "duration IS NULL OR duration IN ('moment', 'day', 'weekend', 'week', 'month')",
            name=op.f("ck_side_quests_duration"),
        ),
        sa.CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_side_quests_rating_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_side_quests")),
    )
    bind = op.get_bind()
    for title, minutes, km in TRIPS:
        bind.execute(
            sa.text(
                "INSERT INTO side_quests (title, category, duration, travel_minutes, distance_km, active,"
                " done_before_app, created_at) VALUES (:title, 'trip', 'day', :minutes, :km, false, false, now())"
            ),
            {"title": title, "minutes": minutes, "km": km},
        )


def downgrade() -> None:
    op.drop_table("side_quests")
