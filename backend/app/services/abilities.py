"""Dovednosti (E37, docs/habit-journal-module-spec.md): abilities the hero picked up, named in habit entries.

An ability is found by its key (the name without case, diacritics and extra spaces), so "lezeni" and "Lezení" are
one. Counts, first / last day and the level come live from the entries; the first entry of an ability pays
NEW_ABILITY_XP to Mysl on its day (an untick or a merge moves or removes it, like every ledger gain).
"""

import datetime as dt
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.habits import Ability, Habit, HabitLog

NEW_ABILITY_XP = 25  # (tune)
SKILL = "mind"
# (entries needed, level name) (tune)
LEVELS = [(1, "Nováček"), (3, "Začátečník"), (10, "Pokročilý"), (25, "Zkušený")]
MAX_NAME = 60
MIN_SIMILARITY = 0.3


def ability_key(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def clean_name(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME]


def find(session: Session, name: str) -> Ability | None:
    return session.exec(select(Ability).where(Ability.key == ability_key(name))).first()


def find_or_create(session: Session, name: str) -> Ability:
    """Idempotent by key, so an ability typed in offline and replayed twice is created once."""
    ability = find(session, name)
    if ability is None:
        ability = Ability(name=clean_name(name), key=ability_key(name))
        session.add(ability)
        session.flush()
    return ability


def resolve(session: Session, name: str) -> tuple[Ability | None, list[str]]:
    """For the coach: the ability with this key, else up to 3 similar names (pg_trgm, unaccented); with no
    similar one, None and [] mean "a new dovednost"."""
    if exact := find(session, name):
        return exact, []

    def normalized(value):  # SQL expression
        return func.f_unaccent(func.lower(value))

    score = func.greatest(
        func.similarity(normalized(Ability.name), normalized(name)),
        func.word_similarity(normalized(name), normalized(Ability.name)),
    )
    rows = session.exec(select(Ability.name).where(score >= MIN_SIMILARITY).order_by(score.desc()).limit(3))
    return None, list(rows)


def first_days(session: Session, on: dt.date) -> dict[str, tuple[dt.date, str]]:
    """Ability key -> (the day of its first entry up to `on`, its name), for the bucket list and quests."""
    query = (
        select(Ability.key, Ability.name, func.min(HabitLog.date))
        .join(HabitLog, col(HabitLog.ability_id) == Ability.id)
        .where(col(HabitLog.date) <= on)
        .group_by(col(Ability.id))
    )
    return {key: (day, name) for key, name, day in session.exec(query)}


def level_of(count: int) -> tuple[int, str]:
    """1-based level and its name for a number of entries."""
    level, name = 1, LEVELS[0][1]
    for index, (needed, label) in enumerate(LEVELS, start=1):
        if count >= needed:
            level, name = index, label
    return level, name


@dataclass
class AbilityEntry:
    date: dt.date
    habit_id: int
    habit_title: str
    note: str | None
    rating: int | None


@dataclass
class AbilityState:
    ability: Ability
    entries: list[AbilityEntry] = field(default_factory=list)  # oldest first

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def first_on(self) -> dt.date | None:
        return self.entries[0].date if self.entries else None

    @property
    def last_on(self) -> dt.date | None:
        return self.entries[-1].date if self.entries else None


def load(session: Session, on: dt.date | None = None) -> list[AbilityState]:
    """Every ability with its entries up to `on`, the most recently used first (unused ones last, by name)."""
    states = {a.id: AbilityState(a) for a in session.exec(select(Ability)).all()}
    query = (
        select(HabitLog, Habit.title)
        .join(Habit, col(Habit.id) == HabitLog.habit_id)
        .where(col(HabitLog.ability_id).is_not(None))
        .order_by(col(HabitLog.date), col(HabitLog.created_at))
    )
    if on is not None:
        query = query.where(col(HabitLog.date) <= on)
    for log, title in session.exec(query):
        states[log.ability_id].entries.append(AbilityEntry(log.date, log.habit_id, title, log.note, log.rating))
    return sorted(
        states.values(),
        key=lambda s: (s.last_on is None, -(s.last_on or dt.date.min).toordinal(), s.ability.key),
    )


@dataclass
class Gain:
    date: dt.date
    amount: int
    kind: str
    text: str


def gains(states: list[AbilityState], on: dt.date) -> list[Gain]:
    return [
        Gain(s.first_on, NEW_ABILITY_XP, "ability_new", f"Nová dovednost: {s.ability.name}")
        for s in states
        if s.first_on and s.first_on <= on
    ]


def merge(session: Session, source: Ability, target: Ability) -> None:
    """Moves every entry of `source` to `target` and deletes `source`."""
    for log in session.exec(select(HabitLog).where(HabitLog.ability_id == source.id)):
        log.ability_id = target.id
        session.add(log)
    session.flush()
    session.delete(source)
    session.commit()
