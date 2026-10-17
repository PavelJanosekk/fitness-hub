"""Exercise lookup by name: exact (case- and accent-insensitive) first, then pg_trgm candidates."""

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.gym import Exercise

MIN_SIMILARITY = 0.3


@dataclass
class ExerciseMatch:
    exact: Exercise | None
    candidates: list[tuple[Exercise, float]]  # best first


def _normalized(value):  # SQL expression
    return func.f_unaccent(func.lower(value))


def resolve_exercise(session: Session, name: str, limit: int = 3) -> ExerciseMatch:
    query = name.strip()
    exact = session.exec(select(Exercise).where(_normalized(Exercise.name) == _normalized(query))).first()
    if exact is not None:
        return ExerciseMatch(exact=exact, candidates=[(exact, 1.0)])
    # word_similarity scores "bench" inside "Bench Press (Barbell)" highly; similarity handles typos
    score = func.greatest(
        func.similarity(_normalized(Exercise.name), _normalized(query)),
        func.word_similarity(_normalized(query), _normalized(Exercise.name)),
    )
    rows = session.exec(select(Exercise, score).where(score >= MIN_SIMILARITY).order_by(score.desc()).limit(limit))
    return ExerciseMatch(exact=None, candidates=[(exercise, round(float(s), 2)) for exercise, s in rows])
