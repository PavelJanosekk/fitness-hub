"""Bucket list (E36, docs/bucket-list-module-spec.md)."""

import datetime as dt

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.data.continents import CONTINENT_NAMES, CONTINENT_OF
from app.database import SessionDep
from app.models.bucket import BucketAutoRule, BucketItem, BucketStep, VisitedCountry
from app.models.gym import Exercise
from app.schemas.bucket import (
    BucketBoard,
    BucketItemCreate,
    BucketItemRead,
    BucketItemUpdate,
    CountryRead,
    CountryState,
    Rarity,
    StepCreate,
    StepRead,
    StepUpdate,
    YearQuest,
)
from app.services import bucket as svc
from app.timeutils import today

router = APIRouter(prefix="/api/bucket", tags=["bucket"])

REQUIRED = {"title", "category", "rarity", "done_before_app", "country_codes"}  # null = unchanged


def _get(session: Session, item_id: int) -> BucketItem:
    item = session.get(BucketItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


def _check_day(day: dt.date | None) -> None:
    if day is not None and day > today() + dt.timedelta(days=1):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Cannot complete a future day")


def _validate(session: Session, item: BucketItem) -> None:
    unknown = [c for c in item.country_codes if c not in CONTINENT_OF]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown country codes: {', '.join(unknown)}")
    item.country_codes = list(dict.fromkeys(item.country_codes))
    if item.auto_rule == BucketAutoRule.exercise:
        if item.auto_exercise_id is None or session.get(Exercise, item.auto_exercise_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The exercise rule needs an existing exercise")
    else:
        item.auto_exercise_id = None
    if item.auto_rule not in (BucketAutoRule.hike, BucketAutoRule.continents):
        item.auto_threshold = None
    if item.done_before_app:
        item.done_on = None


def _read(state: svc.ItemState, exercises: dict[int, str]) -> BucketItemRead:
    item = state.item
    return BucketItemRead(
        **item.model_dump(exclude={"country_codes"}),
        country_codes=list(item.country_codes),
        auto_exercise_name=exercises.get(item.auto_exercise_id or 0),
        steps=[StepRead(id=s.id or 0, position=s.position, title=s.title, done_on=s.done_on) for s in state.steps],
        done=state.done,
        completed_on=state.done_on,
        source=state.source,
        auto_label=state.auto_label,
        auto_progress=state.auto_progress,
        xp=state.xp if state.done else svc.RARITIES[item.rarity][1],
        goal_xp=state.goal_xp,
    )


@router.get("", response_model=BucketBoard)
def board(session: SessionDep) -> BucketBoard:
    """Every item with its derived state, the world map and the year quest; the client filters and groups."""
    on = today()
    state = svc.load(session, on)
    ids = {s.item.auto_exercise_id for s in state.items if s.item.auto_exercise_id}
    exercises = dict(session.exec(select(Exercise.id, Exercise.name).where(col(Exercise.id).in_(ids))).all())
    done, reached = svc.year_progress(state, on.year)
    return BucketBoard(
        today=on,
        items=[_read(s, exercises) for s in state.items],
        countries=[CountryRead(**c.__dict__) for c in state.countries],
        continents=state.continents,
        continent_names=CONTINENT_NAMES,
        country_continents=CONTINENT_OF,
        rarities=[Rarity(level=level, name=name, xp=xp) for level, (name, xp) in svc.RARITIES.items()],
        categories={key.value: name for key, name in svc.CATEGORY_NAMES.items()},
        year_quest=YearQuest(
            year=on.year, done=done, target=svc.YEAR_QUEST_ITEMS, xp=svc.YEAR_QUEST_XP, reached_on=reached
        ),
        xp_total=sum(g.amount for g in svc.gains(state, on)),
        step_xp=svc.STEP_XP,
        year_goal_share=svc.YEAR_GOAL_SHARE,
    )


@router.post("", response_model=BucketItemRead, status_code=status.HTTP_201_CREATED)
def create_item(body: BucketItemCreate, session: SessionDep) -> BucketItemRead:
    item = BucketItem(**body.model_dump(exclude={"steps"}))
    _validate(session, item)
    session.add(item)
    session.flush()
    for position, title in enumerate(body.steps):
        session.add(BucketStep(item_id=item.id, position=position, title=title))
    session.commit()
    return _item(session, item.id)


@router.patch("/{item_id}", response_model=BucketItemRead)
def update_item(item_id: int, body: BucketItemUpdate, session: SessionDep) -> BucketItemRead:
    """Edit, complete (done_on), un-complete (done_on null), plan, star; idempotent."""
    item = _get(session, item_id)
    changes = body.model_dump(exclude_unset=True)
    _check_day(changes.get("done_on"))
    for name, value in changes.items():
        if name in REQUIRED and value is None:
            continue
        setattr(item, name, value)
    if changes.get("done_on") is not None:
        item.done_before_app = False
    _validate(session, item)
    session.add(item)
    session.commit()
    return _item(session, item_id)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, session: SessionDep) -> Response:
    session.delete(_get(session, item_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _item(session: Session, item_id: int | None) -> BucketItemRead:
    state = next(s for s in svc.load(session).items if s.item.id == item_id)
    name = session.get(Exercise, state.item.auto_exercise_id) if state.item.auto_exercise_id else None
    return _read(state, {name.id: name.name} if name and name.id else {})


# --- Steps -----------------------------------------------------------------------------------


def _step(session: Session, step_id: int) -> BucketStep:
    step = session.get(BucketStep, step_id)
    if step is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    return step


@router.post("/{item_id}/steps", response_model=BucketItemRead, status_code=status.HTTP_201_CREATED)
def add_step(item_id: int, body: StepCreate, session: SessionDep) -> BucketItemRead:
    _get(session, item_id)
    last = session.exec(select(func.max(BucketStep.position)).where(BucketStep.item_id == item_id)).one()
    session.add(BucketStep(item_id=item_id, title=body.title, position=0 if last is None else last + 1))
    session.commit()
    return _item(session, item_id)


@router.patch("/steps/{step_id}", response_model=BucketItemRead)
def update_step(step_id: int, body: StepUpdate, session: SessionDep) -> BucketItemRead:
    step = _step(session, step_id)
    changes = body.model_dump(exclude_unset=True)
    _check_day(changes.get("done_on"))
    if changes.get("title"):
        step.title = changes["title"]
    if "done_on" in changes:
        step.done_on = changes["done_on"]
    session.add(step)
    session.commit()
    return _item(session, step.item_id)


@router.delete("/steps/{step_id}", response_model=BucketItemRead)
def delete_step(step_id: int, session: SessionDep) -> BucketItemRead:
    step = _step(session, step_id)
    item_id = step.item_id
    session.delete(step)
    session.commit()
    return _item(session, item_id)


# --- World map -------------------------------------------------------------------------------


@router.put("/countries/{code}", response_model=list[CountryRead])
def set_country(code: str, body: CountryState, session: SessionDep) -> list[CountryRead]:
    """Marks / unmarks a country on the map; idempotent. Countries of completed items stay regardless."""
    code = code.upper()
    if code not in CONTINENT_OF:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown country code")
    _check_day(body.visited_on)
    row = session.get(VisitedCountry, code)
    if body.visited:
        # An explicit null = before the app; not sent = keep the known day, today for a new country
        kept = row.visited_on if row else today()
        visited_on = body.visited_on if "visited_on" in body.model_fields_set else kept
        row = row or VisitedCountry(code=code)
        row.visited_on = visited_on
        session.add(row)
    elif row is not None:
        session.delete(row)
    session.commit()
    return [CountryRead(**c.__dict__) for c in svc.load(session).countries]
