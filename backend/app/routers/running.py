import datetime as dt

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.database import SessionDep
from app.models.running import Activity, TrainingPlanItem
from app.schemas.running import ActivityCreate, ActivityRead, PlanItemIn, PlanItemRead
from app.timeutils import today

router = APIRouter(prefix="/api/running", tags=["running"])


def read_activity(activity: Activity) -> ActivityRead:
    read = ActivityRead.model_validate(activity)
    if activity.distance_meters > 0:
        pace = round(activity.duration_seconds / (activity.distance_meters / 1000))
        read.pace_sec_per_km = pace
        read.pace = f"{pace // 60}:{pace % 60:02d}"
    return read


@router.get("/activities", response_model=list[ActivityRead])
def list_activities(
    session: SessionDep, limit: int = Query(50, ge=1, le=500), activity_type: str | None = None
) -> list[ActivityRead]:
    query = select(Activity).order_by(col(Activity.start_time).desc()).limit(limit)
    if activity_type:
        query = query.where(Activity.activity_type == activity_type)
    return [read_activity(a) for a in session.exec(query).all()]


@router.post("/activities", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(body: ActivityCreate, session: SessionDep) -> ActivityRead:
    activity = Activity(**body.model_dump())
    session.add(activity)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Activity with this external_id already exists") from None
    session.refresh(activity)
    return read_activity(activity)


@router.get("/plan", response_model=list[PlanItemRead])
def get_plan(
    session: SessionDep, start_date: dt.date | None = None, end_date: dt.date | None = None
) -> list[PlanItemRead]:
    start = start_date or today()
    end = end_date or start + dt.timedelta(days=27)
    items = session.exec(
        select(TrainingPlanItem)
        .where(col(TrainingPlanItem.planned_date).between(start, end))
        .order_by(col(TrainingPlanItem.planned_date))
    ).all()
    linked_ids = [i.completed_activity_id for i in items if i.completed_activity_id]
    activities = {a.id: a for a in session.exec(select(Activity).where(col(Activity.id).in_(linked_ids)))}
    return [
        PlanItemRead.model_validate(item).model_copy(
            update={"completed_activity": read_activity(activities[item.completed_activity_id])}
            if item.completed_activity_id in activities
            else {}
        )
        for item in items
    ]


@router.post("/plan", response_model=PlanItemRead)
def upsert_plan_item(body: PlanItemIn, session: SessionDep) -> TrainingPlanItem:
    if body.completed_activity_id is not None and session.get(Activity, body.completed_activity_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown completed_activity_id")
    item = session.get(TrainingPlanItem, body.id) if body.id is not None else None
    if body.id is not None and item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan item not found")
    item = item or TrainingPlanItem(planned_date=body.planned_date, title=body.title)
    for field, value in body.model_dump(exclude={"id"}).items():
        setattr(item, field, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/plan/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan_item(item_id: int, session: SessionDep) -> Response:
    item = session.get(TrainingPlanItem, item_id)
    if item is not None:
        session.delete(item)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
