"""Food resolution for dictated meals (nutrition spec §4 + Amendments C6/C7, decision E4).

For each item Gemini extracted: a confirmed alias, the known-food id from the prompt, or an exact name match on a
confirmed food resolves it outright. Otherwise candidates are gathered (local foods by Czech name, USDA by the
English query, OFF for branded products), a Chooser picks one with a confidence, and the meal becomes a draft for
1-tap confirmation. Aliases are written only when the user confirms (`confirm_aliases`), so a wrong automatic
pick never becomes a permanent mapping.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_
from sqlmodel import Session, col, select

from app.models.nutrition import Food, FoodAlias, FoodSource, MealLogItem
from app.services.nutrition import off
from app.services.nutrition.nutrients import MACROS

# Sources the user created or imported from their own diary: confirmed by definition
USER_SOURCES = (FoodSource.custom, FoodSource.kaloricke_tabulky, FoodSource.recipe)
# USDA categories that rarely mean what a Czech home cook says
PENALIZED_CATEGORIES = {"Baby Foods", "Fast Foods", "Restaurant Foods", "American Indian/Alaska Native Foods"}
STOPWORDS = {"and", "or", "of", "the", "a", "in", "to", "for"}
POOL = 40
MAX_CANDIDATES = 8


class MealItemInput(BaseModel):
    """One food in a dictated meal, as Gemini extracts it."""

    user_phrase: str = Field(description="The words the user used for this food, as said (Czech)")
    canonical_name_cs: str = Field(description="Canonical Czech name in nominative, e.g. 'Kuřecí stehno, syrové'")
    amount_g: float = Field(gt=0, le=5000, description="Eaten amount in grams (convert units and portions)")
    usda_query_en: str | None = Field(
        default=None, description="USDA-style English description, e.g. 'Chicken, thigh, meat only, raw'"
    )
    is_branded: bool = Field(default=False, description="A packaged/branded product rather than a basic food")
    brand_search_query: str | None = Field(default=None, description="Product search text for branded items")
    food_id: int | None = Field(default=None, description="Id from the known-foods list when it is that food")


@dataclass
class Candidate:
    """A possible food: an existing row, or an OFF product / web estimate that becomes one on confirmation."""

    ref: str  # "food:<id>" | "off:<ean>" | "web"
    name: str
    source: str
    per_100g: dict[str, float | None]  # macro columns
    brand: str | None = None
    score: float = 0.0
    micronutrients: dict[str, float] = field(default_factory=dict)
    food: Food | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {"ref": self.ref, "name": self.name, "source": self.source, "brand": self.brand}
        return out | {"per_100g": self.per_100g, "micronutrients": self.micronutrients}


@dataclass
class Resolution:
    item: MealItemInput
    food: Food | None = None  # set only when resolved by a confirmed mapping (auto-save eligible)
    via: str | None = None  # "food_id" | "alias" | "exact_name"
    candidates: list[Candidate] = field(default_factory=list)
    chosen: Candidate | None = None
    confidence: float | None = None

    @property
    def confirmed(self) -> bool:
        return self.food is not None


class Chooser(Protocol):
    """Picks among candidates (Gemini in production, deterministic in tests)."""

    def choose(self, resolutions: list[Resolution]) -> list[tuple[int | None, float | None]]:
        """Per resolution: index into its candidates (None = none fits) and a confidence 0-1."""
        ...

    def estimate(self, item: MealItemInput) -> Candidate | None:
        """A per-100 g estimate from the web when no candidate exists (C5); None if unavailable."""
        ...


class TopScoreChooser:
    """Fallback without Gemini: the best-scored candidate, confidence unknown."""

    def choose(self, resolutions: list[Resolution]) -> list[tuple[int | None, float | None]]:
        return [(0 if r.candidates else None, None) for r in resolutions]

    def estimate(self, item: MealItemInput) -> Candidate | None:
        return None


def normalize(phrase: str) -> str:
    """Alias key: lowercase, no diacritics, single spaces (C7). Matches f_unaccent(lower()) for Czech."""
    decomposed = unicodedata.normalize("NFKD", phrase.lower())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", plain).strip()


def _sql_normalized(column):
    return func.f_unaccent(func.lower(column))


def _per_100g(food: Food) -> dict[str, float | None]:
    return {n.key: getattr(food, n.key) for n in MACROS}


def food_candidate(food: Food, score: float = 0.0) -> Candidate:
    return Candidate(f"food:{food.id}", food.name, food.source, _per_100g(food), food.brand, score, food=food)


def is_confirmed_food(session: Session, food: Food) -> bool:
    """User-made or imported, already eaten (every saved meal item was confirmed or auto-saved from a confirmed
    mapping), or reachable through a confirmed alias."""
    if food.source in USER_SOURCES:
        return True
    eaten = exists().where(MealLogItem.food_id == food.id)
    aliased = exists().where(FoodAlias.food_id == food.id, col(FoodAlias.confirmed))
    return bool(session.exec(select(or_(eaten, aliased))).one())


def _confirmed_match(session: Session, item: MealItemInput) -> tuple[Food | None, str | None]:
    if item.food_id is not None:
        food = session.get(Food, item.food_id)
        if food is not None and is_confirmed_food(session, food):
            return food, "food_id"
    keys = {normalize(item.user_phrase), normalize(item.canonical_name_cs)}
    alias = session.exec(
        select(FoodAlias).where(col(FoodAlias.alias_normalized).in_(keys), col(FoodAlias.confirmed))
    ).first()
    if alias is not None:
        return session.get(Food, alias.food_id), "alias"
    exact = session.exec(
        select(Food).where(_sql_normalized(Food.name_cs) == normalize(item.canonical_name_cs)).order_by(col(Food.id))
    ).all()
    for food in exact:
        if is_confirmed_food(session, food):
            return food, "exact_name"
    return None, None


def _words(value: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", normalize(value))
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in STOPWORDS]


def _tokens(value: str) -> set[str]:
    return set(_words(value))


def search_usda(session: Session, query: str, limit: int = MAX_CANDIDATES) -> list[tuple[Food, float]]:
    """USDA foods for an English description: a trigram + full-text pool, re-ranked by how much of the query a
    name covers (full-text alone drops words like "only"; trigrams alone favour short names)."""
    wanted = _tokens(query)
    if not wanted:
        return []
    usda = Food.source == FoodSource.usda
    trigram = func.similarity(func.lower(Food.name_en), query.lower())
    pool = {f.id: f for f in session.exec(select(Food).where(usda).order_by(trigram.desc()).limit(POOL))}
    tsquery = func.to_tsquery("english", " | ".join(sorted(wanted)))
    vector = func.to_tsvector("english", Food.name_en)
    ranked = select(Food).where(usda, vector.op("@@")(tsquery)).order_by(func.ts_rank_cd(vector, tsquery).desc())
    pool |= {f.id: f for f in session.exec(ranked.limit(POOL))}

    head = _words(query)[0]

    def score(food: Food) -> float:
        words = _words(food.name_en or "")
        have = set(words)
        value = len(wanted & have) / len(wanted) - 0.02 * len(have - wanted)
        # USDA names lead with the food itself ("Milk, whole, ..."), so a matching head word is a strong signal
        value += 0.1 if words and words[0] == head else 0
        return round(value - (0.15 if food.category in PENALIZED_CATEGORIES else 0), 3)

    # SR Legacy and Foundation share some names: keep the copy with more known micronutrients
    best: dict[str, Food] = {}
    for food in pool.values():
        kept = best.get(food.name_en or "")
        if kept is None or len(food.micronutrients) > len(kept.micronutrients):
            best[food.name_en or ""] = food
    scored = sorted(((f, score(f)) for f in best.values()), key=lambda pair: -pair[1])
    return [(f, s) for f, s in scored[:limit] if s > 0]


def search_local(session: Session, name_cs: str, limit: int = 5) -> list[tuple[Food, float]]:
    """Foods with a Czech name (eaten USDA foods, OFF products, KT, custom) by accent-insensitive similarity."""
    query = normalize(name_cs)
    score = func.greatest(
        func.similarity(_sql_normalized(Food.name_cs), query),
        func.word_similarity(query, _sql_normalized(func.concat_ws(" ", Food.name_cs, Food.brand))),
    )
    rows = session.exec(
        select(Food, score).where(col(Food.name_cs).is_not(None), score >= 0.35).order_by(score.desc()).limit(limit)
    )
    return [(food, round(float(s), 3)) for food, s in rows]


def gather_candidates(session: Session, http: httpx.Client | None, item: MealItemInput) -> list[Candidate]:
    seen: set[str] = set()
    out: list[Candidate] = []

    def add(candidate: Candidate) -> None:
        if candidate.ref not in seen:
            seen.add(candidate.ref)
            out.append(candidate)

    for food, s in search_local(session, item.canonical_name_cs):
        add(food_candidate(food, s))
    if item.is_branded and item.brand_search_query and http is not None:
        try:
            products = off.search(http, item.brand_search_query)
        except httpx.HTTPError:
            products = []  # OFF down: local and USDA candidates still work
        for p in products[:5]:
            existing = session.exec(select(Food).where(Food.ean == p.ean)).first()
            add(food_candidate(existing) if existing else _off_candidate(p))
    if item.usda_query_en:
        for food, s in search_usda(session, item.usda_query_en):
            add(food_candidate(food, s))
    return out[:MAX_CANDIDATES]


def _off_candidate(product: off.OffProduct) -> Candidate:
    per_100g = {n.key: product.values.get(n.key) for n in MACROS}
    return Candidate(
        f"off:{product.ean}",
        product.name,
        FoodSource.openfoodfacts,
        per_100g,
        product.brand,
        0.5,
        product.micronutrients,
    )


def resolve_items(
    session: Session, http: httpx.Client | None, items: list[MealItemInput], chooser: Chooser
) -> list[Resolution]:
    resolutions = []
    for item in items:
        food, via = _confirmed_match(session, item)
        resolution = Resolution(item, food=food, via=via)
        if food is not None:
            resolution.chosen = food_candidate(food, 1.0)
        else:
            resolution.candidates = gather_candidates(session, http, item)
        resolutions.append(resolution)

    open_ = [r for r in resolutions if not r.confirmed]
    for resolution in open_:
        if not resolution.candidates and (estimate := chooser.estimate(resolution.item)) is not None:
            resolution.candidates = [estimate]
    if open_:
        for resolution, (index, confidence) in zip(open_, chooser.choose(open_), strict=True):
            if index is not None and 0 <= index < len(resolution.candidates):
                resolution.chosen = resolution.candidates[index]
            resolution.confidence = confidence
    return resolutions


def confirm_aliases(session: Session, item: MealItemInput, food: Food) -> None:
    """The user confirmed `food` for this item: both phrases now map to it (new or re-pointed, confirmed).
    A USDA food gets the Czech name the first time it's used, so it shows and matches in Czech from now on."""
    for key in {normalize(item.user_phrase), normalize(item.canonical_name_cs)}:
        alias = session.exec(select(FoodAlias).where(FoodAlias.alias_normalized == key)).first()
        alias = alias or FoodAlias(alias_normalized=key, food_id=food.id)  # type: ignore[arg-type]
        alias.food_id, alias.confirmed = food.id, True  # type: ignore[assignment]
        session.add(alias)
    if food.name_cs is None:
        food.name_cs = item.canonical_name_cs
        session.add(food)


def materialize(session: Session, candidate: Candidate, item: MealItemInput) -> Food:
    """The Food behind a confirmed candidate, creating it for an OFF product or a web estimate."""
    if candidate.ref.startswith("food:"):
        food = session.get(Food, int(candidate.ref.removeprefix("food:")))
        if food is None:
            raise LookupError(candidate.ref)
        return food
    values = {k: v for k, v in candidate.per_100g.items() if v is not None}
    if candidate.ref.startswith("off:"):
        ean = candidate.ref.removeprefix("off:")
        product = off.OffProduct(ean, candidate.name, candidate.brand, values, candidate.micronutrients)
        return off.save_product(session, product)
    food = Food(
        name_cs=item.canonical_name_cs,
        brand=candidate.brand,
        source=FoodSource.web_estimate,
        micronutrients=candidate.micronutrients,
        **values,
    )
    session.add(food)
    session.flush()
    return food
