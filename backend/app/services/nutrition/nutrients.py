"""The nutrients the app tracks (nutrition spec §2 + Amendments C1/C2/C9).

Macros are columns on `foods`; micros are keys of `foods.micronutrients`, present only when the value is known.
All values are per 100 g. `usda` lists the USDA FoodData Central nutrient ids: the nutrient is the sum of its
components, and each component takes the first id a food has (fallback chain), times `usda_factor`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Nutrient:
    key: str
    label_cs: str
    unit: str
    usda: tuple[tuple[int, ...], ...]
    # Adult daily reference: EU NRV / reference intake (Reg. 1169/2011, Annex XIII); fibre = EFSA adequate intake.
    # None = no single reference (shown as an amount only).
    reference: float | None = None
    usda_factor: float = 1.0


MACROS: tuple[Nutrient, ...] = (
    # Energy: measured 1008, else Atwater specific 2048, else Atwater general 2047 (Foundation often lacks 1008)
    Nutrient("kcal", "Energie", "kcal", ((1008, 2048, 2047),), 2000),
    Nutrient("protein_g", "Bílkoviny", "g", ((1003,),), 50),
    Nutrient("carbs_g", "Sacharidy", "g", ((1005, 1050),), 260),
    Nutrient("fat_g", "Tuky", "g", ((1004,),), 70),
    Nutrient("sugar_g", "Cukry", "g", ((2000, 1063),), 90),
    Nutrient("saturated_fat_g", "Nasycené mastné kyseliny", "g", ((1258,),), 20),
    Nutrient("fiber_g", "Vláknina", "g", ((1079,),), 25),
    # USDA has no salt: salt = sodium * 2.5 (mg → g)
    Nutrient("salt_g", "Sůl", "g", ((1093,),), 6, usda_factor=2.5 / 1000),
)

# Every food must have these (Amendments: required columns); the rest stay null when unknown
REQUIRED_MACROS = ("kcal", "protein_g", "carbs_g", "fat_g")

MICROS: tuple[Nutrient, ...] = (
    Nutrient("vitamin_a_ug", "Vitamín A", "µg", ((1106,),), 800),
    Nutrient("vitamin_c_mg", "Vitamín C", "mg", ((1162,),), 80),
    Nutrient("vitamin_d_ug", "Vitamín D", "µg", ((1114,),), 5),  # 1110 is IU: ignored
    Nutrient("vitamin_e_mg", "Vitamín E", "mg", ((1109,),), 12),
    Nutrient("vitamin_k_ug", "Vitamín K", "µg", ((1185,),), 75),
    Nutrient("vitamin_b1_mg", "Thiamin (B1)", "mg", ((1165,),), 1.1),
    Nutrient("vitamin_b2_mg", "Riboflavin (B2)", "mg", ((1166,),), 1.4),
    Nutrient("vitamin_b3_mg", "Niacin (B3)", "mg", ((1167,),), 16),
    Nutrient("vitamin_b5_mg", "Kyselina pantothenová (B5)", "mg", ((1170,),), 6),
    Nutrient("vitamin_b6_mg", "Vitamín B6", "mg", ((1175,),), 1.4),
    # Folate as DFE (the unit DRIs use), else total folate
    Nutrient("vitamin_b9_ug", "Folát (B9)", "µg", ((1190, 1177),), 200),
    Nutrient("vitamin_b12_ug", "Vitamín B12", "µg", ((1178,),), 2.5),
    Nutrient("calcium_mg", "Vápník", "mg", ((1087,),), 800),
    Nutrient("iron_mg", "Železo", "mg", ((1089,),), 14),
    Nutrient("magnesium_mg", "Hořčík", "mg", ((1090,),), 375),
    Nutrient("phosphorus_mg", "Fosfor", "mg", ((1091,),), 700),
    Nutrient("potassium_mg", "Draslík", "mg", ((1092,),), 2000),
    Nutrient("sodium_mg", "Sodík", "mg", ((1093,),)),
    Nutrient("zinc_mg", "Zinek", "mg", ((1095,),), 10),
    Nutrient("copper_mg", "Měď", "mg", ((1098,),), 1),
    Nutrient("manganese_mg", "Mangan", "mg", ((1101,),), 2),
    Nutrient("selenium_ug", "Selen", "µg", ((1103,),), 55),
    # Approximations: ALA (or undifferentiated 18:3) + EPA + DHA + DPA; LA (or undifferentiated 18:2) + AA
    Nutrient("omega3_g", "Omega-3 (přibližně)", "g", ((1404, 1270), (1278,), (1272,), (1280,))),
    Nutrient("omega6_g", "Omega-6 (přibližně)", "g", ((1316, 1269), (1271,))),
)

ALL: tuple[Nutrient, ...] = MACROS + MICROS
BY_KEY: dict[str, Nutrient] = {n.key: n for n in ALL}
MICRO_KEYS = frozenset(n.key for n in MICROS)
USDA_IDS = frozenset(i for n in ALL for component in n.usda for i in component)


def from_usda(amounts: dict[int, float]) -> dict[str, float]:
    """Map a food's USDA amounts (nutrient id → amount per 100 g) to our keys. Unknown nutrients are left out."""
    values: dict[str, float] = {}
    for nutrient in ALL:
        parts = []
        for component in nutrient.usda:
            found = next((amounts[i] for i in component if i in amounts), None)
            if found is not None:
                parts.append(found)
        # A sum with a missing component would understate the total, but those are approximations by design;
        # a nutrient with no component at all stays unknown
        if parts:
            values[nutrient.key] = round(sum(parts) * nutrient.usda_factor, 4)
    return values
