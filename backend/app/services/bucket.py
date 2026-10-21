"""Bucket list (E36, docs/bucket-list-module-spec.md): item state, auto rules, countries and the XP it pays.

Everything is derived live, like habits and the XP ledger: an auto rule (marathon, gym exercise, hike, continents)
completes an item on the first day the data shows it, so a late Strava sync or an edit rewrites it consistently.

XP (tune): an item pays by rarity on its completion day (skill Dobrodružství). No XP for items done before the app
(`done_before_app`) or completed more than LATE_DAYS before they were added to the list (no retroactive XP, B6).
A starred year goal done in its year pays YEAR_GOAL_SHARE on top; YEAR_QUEST_ITEMS paying items in one calendar
year pay YEAR_QUEST_XP once; each finished step of a bigger item pays STEP_XP. No penalties.
"""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.data.continents import CONTINENT_OF
from app.models.bucket import BucketAutoRule, BucketCategory, BucketItem, BucketStep, VisitedCountry
from app.models.coach import Race
from app.models.gym import Exercise, Workout, WorkoutSet
from app.models.running import Activity
from app.models.side_quests import SideQuest
from app.services import abilities as ab
from app.services.run_analysis import RUN_TYPES
from app.timeutils import local_date, today

RARITIES = {1: ("Běžná", 50), 2: ("Vzácná", 150), 3: ("Epická", 400), 4: ("Legendární", 1000)}
STEP_XP = 25
YEAR_GOAL_SHARE = 0.5
YEAR_QUEST_ITEMS = 5
YEAR_QUEST_XP = 500
LATE_DAYS = 7  # a completion up to a week before the item was added still pays (logged a bit late)
SKILL = "adventure"

MARATHON_KM = 42.0
RACE_MARATHON_KM = 40.0  # GPS often reads a little short on race day
HIKE_TYPES = ("Hike", "Walk")
HIKE_ELEVATION_M = 1000.0
CONTINENTS_TARGET = 7

CATEGORY_NAMES = {
    BucketCategory.travel: "Cestování",
    BucketCategory.expedition: "Výpravy",
    BucketCategory.experience: "Zážitky",
    BucketCategory.adrenaline: "Adrenalin",
    BucketCategory.sport: "Sport & pohyb",
    BucketCategory.skill: "Dovednosti",
    BucketCategory.food: "Jídlo & pití",
    BucketCategory.wellbeing: "Tělo & mysl",
}


@dataclass
class ItemState:
    item: BucketItem
    steps: list[BucketStep]
    done_on: dt.date | None = None  # effective completion day (manual or auto); null when done before the app
    source: str | None = None  # "manual" | "auto" | "before"; null = open
    auto_label: str | None = None  # what the auto rule saw, e.g. "Běh 42,4 km"
    auto_progress: str | None = None  # an open auto item's progress, e.g. "2 / 7 kontinentů"
    xp: int = 0  # the item's own XP (rarity), 0 when it doesn't pay
    goal_xp: int = 0  # year-goal bonus

    @property
    def done(self) -> bool:
        return self.source is not None

    @property
    def added_on(self) -> dt.date:
        return local_date(self.item.created_at)

    def pays(self, day: dt.date) -> bool:
        return day >= self.added_on - dt.timedelta(days=LATE_DAYS)


@dataclass
class Country:
    code: str
    continent: str | None
    visited_on: dt.date | None  # earliest known; null = before the app
    on_map: bool  # marked on the map by hand (else only through completed items)
    since: dt.date  # for badges: visited_on, else the day it got into the app
    items: list[str] = field(default_factory=list)


@dataclass
class BucketState:
    items: list[ItemState]
    countries: list[Country]
    continents: dict[str, dt.date | None]  # visited continent -> first day (null = before the app)


def _first(dates) -> tuple[dt.date, str] | None:
    return min(dates, default=None, key=lambda pair: pair[0])


def _km(meters: float) -> str:
    return f"{meters / 1000:.1f}".replace(".", ",")


def _marathon(session: Session, on: dt.date) -> tuple[dt.date, str] | None:
    race_days = set(session.exec(select(Race.date).where(col(Race.hidden).is_(False))).all())
    found = []
    for start, meters in session.exec(
        select(Activity.start_time, Activity.distance_meters).where(
            col(Activity.activity_type).in_(RUN_TYPES), Activity.distance_meters >= RACE_MARATHON_KM * 1000
        )
    ):
        day = local_date(start)
        if day <= on and (meters >= MARATHON_KM * 1000 or day in race_days):
            found.append((day, f"Běh {_km(meters)} km"))
    return _first(found)


def _exercise(session: Session, exercise_id: int, on: dt.date) -> tuple[dt.date, str] | None:
    rows = session.exec(
        select(Workout.started_at, Exercise.name)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .where(WorkoutSet.exercise_id == exercise_id, col(WorkoutSet.completed))
    ).all()
    return _first((d, f"Gym: {name}") for start, name in rows if (d := local_date(start)) <= on)


def _hike(session: Session, threshold: float, on: dt.date) -> tuple[dt.date, str] | None:
    rows = session.exec(
        select(Activity.start_time, Activity.elevation_gain_m).where(
            col(Activity.activity_type).in_(HIKE_TYPES), Activity.elevation_gain_m >= threshold
        )
    ).all()
    label = "Túra s převýšením {:,.0f}\u00a0m"
    return _first(
        (d, label.format(gain).replace(",", "\u00a0")) for start, gain in rows if (d := local_date(start)) <= on
    )


def _sort_key(day: dt.date | None) -> dt.date:
    return day or dt.date.min  # unknown (before the app) sorts first


def _countries(session: Session, states: list[ItemState]) -> list[Country]:
    by_code: dict[str, Country] = {}

    def visit(code: str, day: dt.date | None, on_map: bool, since: dt.date, item: str | None = None) -> None:
        country = by_code.setdefault(code, Country(code, CONTINENT_OF.get(code), day, on_map, since))
        if _sort_key(day) < _sort_key(country.visited_on):
            country.visited_on = day
        country.since = min(country.since, since)
        country.on_map = country.on_map or on_map
        if item:
            country.items.append(item)

    for row in session.exec(select(VisitedCountry)):
        visit(row.code, row.visited_on, True, row.visited_on or local_date(row.created_at))
    for state in states:
        if state.done:
            for code in state.item.country_codes:
                visit(code, state.done_on, False, counted_on(state), state.item.title)
    return sorted(by_code.values(), key=lambda c: c.code)


def _continents(countries: list[Country]) -> dict[str, dt.date | None]:
    result: dict[str, dt.date | None] = {}
    for country in countries:
        if country.continent is None:
            continue
        if country.continent not in result or _sort_key(country.visited_on) < _sort_key(result[country.continent]):
            result[country.continent] = country.visited_on
    return result


def load(session: Session, on: dt.date | None = None) -> BucketState:
    on = on or today()
    items = session.exec(select(BucketItem).order_by(col(BucketItem.id))).all()
    steps: dict[int, list[BucketStep]] = {}
    for step in session.exec(select(BucketStep).order_by(col(BucketStep.position), col(BucketStep.id))):
        steps.setdefault(step.item_id, []).append(step)
    states = [ItemState(item, steps.get(item.id or 0, [])) for item in items]

    pending: list[ItemState] = []
    learned = ab.first_days(session, on)
    for state in states:
        item = state.item
        if item.done_before_app:
            state.source = "before"
        elif item.done_on is not None and item.done_on <= on:
            state.done_on, state.source = item.done_on, "manual"
        elif item.auto_rule == BucketAutoRule.continents:
            pending.append(state)  # needs the other items' countries first
        elif found := _auto(session, item, on):
            state.done_on, state.source, state.auto_label = found[0], "auto", found[1]
        elif (
            item.category == BucketCategory.skill
            and not item.auto_rule
            and (found := learned.get(ab.ability_key(item.title)))
        ):
            # A dovednost of the same name logged in the routine (E37)
            state.done_on, state.source, state.auto_label = found[0], "auto", f"Dovednost: {found[1]}"

    countries = _countries(session, states)
    continents = _continents(countries)
    for state in pending:
        target = int(state.item.auto_threshold or CONTINENTS_TARGET)
        days = sorted(continents.values(), key=_sort_key)
        if len(days) >= target:
            reached = days[target - 1]
            state.done_on, state.source = reached, "auto" if reached else "before"
            state.auto_label = f"{target} kontinentů"
        else:
            state.auto_progress = f"{len(days)} / {target} kontinentů"

    for state in states:
        if state.source in ("manual", "auto") and state.done_on and state.pays(state.done_on):
            state.xp = RARITIES[state.item.rarity][1]
            if state.item.year_goal == state.done_on.year:
                state.goal_xp = round(state.xp * YEAR_GOAL_SHARE)
    return BucketState(states, countries, continents)


def _auto(session: Session, item: BucketItem, on: dt.date) -> tuple[dt.date, str] | None:
    if item.auto_rule == BucketAutoRule.marathon:
        return _marathon(session, on)
    if item.auto_rule == BucketAutoRule.exercise and item.auto_exercise_id is not None:
        return _exercise(session, item.auto_exercise_id, on)
    if item.auto_rule == BucketAutoRule.hike:
        return _hike(session, item.auto_threshold or HIKE_ELEVATION_M, on)
    return None


@dataclass
class Gain:
    date: dt.date
    amount: int
    kind: str
    text: str


def gains(state: BucketState, on: dt.date) -> list[Gain]:
    """Everything the bucket list pays, for the XP ledger (all to the Dobrodružství skill)."""
    result: list[Gain] = []
    by_year: dict[int, list[dt.date]] = {}
    for s in state.items:
        item = s.item
        if s.xp and s.done_on and s.done_on <= on:
            rarity = RARITIES[item.rarity][0]
            result.append(Gain(s.done_on, s.xp, "bucket", f"Bucket list: {item.title} ({rarity})"))
            if s.goal_xp:
                result.append(Gain(s.done_on, s.goal_xp, "bucket_goal", f"Letošní cíl splněn: {item.title}"))
            by_year.setdefault(s.done_on.year, []).append(s.done_on)
        for step in s.steps:
            if step.done_on and step.done_on <= on and s.pays(step.done_on):
                result.append(Gain(step.done_on, STEP_XP, "bucket_step", f"Krok: {item.title} · {step.title}"))
    for year, days in by_year.items():
        if len(days) >= YEAR_QUEST_ITEMS:
            reached = sorted(days)[YEAR_QUEST_ITEMS - 1]
            text = f"Rok dobrodružství {year}: {YEAR_QUEST_ITEMS} splněných položek bucket listu"
            result.append(Gain(reached, YEAR_QUEST_XP, "bucket_year", text))
    return result


def year_progress(state: BucketState, year: int) -> tuple[int, dt.date | None]:
    """Paying items done in `year` and the day the year quest was reached."""
    days = sorted(s.done_on for s in state.items if s.xp and s.done_on and s.done_on.year == year)
    return len(days), days[YEAR_QUEST_ITEMS - 1] if len(days) >= YEAR_QUEST_ITEMS else None


def counted_on(s: ItemState) -> dt.date:
    """For badges and statistics: items done before the app count from the day they were added."""
    return s.done_on or s.added_on


MIN_SIMILARITY = 0.3


def resolve(session: Session, title: str) -> tuple[BucketItem | None, list[tuple[BucketItem, float]]]:
    """Item by title: exact (case- and accent-insensitive) match, else pg_trgm candidates (best first)."""
    return resolve_title(session, BucketItem, title)


def resolve_title[T: (BucketItem, SideQuest)](
    session: Session, model: type[T], title: str
) -> tuple[T | None, list[tuple[T, float]]]:
    """A row of `model` by its title (bucket items, side quests): exact match, else trigram candidates."""

    def normalized(value):  # SQL expression
        return func.f_unaccent(func.lower(value))

    query = title.strip()
    exact = session.exec(select(model).where(normalized(model.title) == normalized(query))).first()
    if exact is not None:
        return exact, [(exact, 1.0)]
    score = func.greatest(
        func.similarity(normalized(model.title), normalized(query)),
        func.word_similarity(normalized(query), normalized(model.title)),
    )
    rows = session.exec(select(model, score).where(score >= MIN_SIMILARITY).order_by(score.desc()).limit(3))
    return None, [(row, round(float(s), 2)) for row, s in rows]
