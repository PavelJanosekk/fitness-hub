import datetime as dt
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.database import SessionDep
from app.models.coach import TrainingDay, TrainingWeek
from app.models.running import Activity, ActivityMetrics, ActivityStream, TrainingPlanItem
from app.routers.integrations import HttpDep
from app.schemas.running import (
    ActivityCreate,
    ActivityRead,
    PlanDayRead,
    PlanItemIn,
    PlanItemRead,
    PlanWeekRead,
    RunDetail,
    RunStats,
)
from app.services import strava_client as strava
from app.services.run_analysis import RUN_TYPES, current_lthr, is_heat
from app.services.run_detail import run_detail
from app.services.run_stats import run_stats
from app.timeutils import day_bounds, today

router = APIRouter(prefix="/api/running", tags=["running"])
log = logging.getLogger(__name__)


def read_activity(activity: Activity, metrics: ActivityMetrics | None = None) -> ActivityRead:
    read = ActivityRead.model_validate(activity)
    read.heat = is_heat(activity)
    if activity.distance_meters > 0:
        pace = round(activity.duration_seconds / (activity.distance_meters / 1000))
        read.pace_sec_per_km = pace
        read.pace = f"{pace // 60}:{pace % 60:02d}"
    if metrics is not None:
        zones = metrics.zone_seconds or {}
        read.gap_sec_per_km = metrics.gap_s_per_km
        read.ef_gap = metrics.ef_gap
        read.decoupling_pct = metrics.decoupling_pct
        read.pct_above_easy = metrics.pct_above_easy
        read.z4_minutes = round(zones["z4"] / 60, 1) if "z4" in zones else None
    return read


@router.get("/activities", response_model=list[ActivityRead])
def list_activities(
    session: SessionDep, limit: int = Query(50, ge=1, le=500), activity_type: str | None = None
) -> list[ActivityRead]:
    query = (
        select(Activity, ActivityMetrics)
        .outerjoin(ActivityMetrics, col(ActivityMetrics.activity_id) == Activity.id)
        .order_by(col(Activity.start_time).desc())
        .limit(limit)
    )
    if activity_type:
        query = query.where(Activity.activity_type == activity_type)
    return [read_activity(a, m) for a, m in session.exec(query).all()]


@router.get("/activities/{activity_id}", response_model=RunDetail)
def get_activity_detail(activity_id: int, session: SessionDep, http: HttpDep) -> RunDetail:
    """The run detail page. Missing or outdated streams are fetched from Strava first (best effort)."""
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
    try:
        strava.refresh_run_streams(session, http, activity)
    except (strava.StravaError, httpx.HTTPError) as exc:
        session.rollback()
        log.warning("Run detail %s: streams not refreshed (%s)", activity_id, exc)
    metrics = session.get(ActivityMetrics, activity_id)
    detail = run_detail(activity, session.get(ActivityStream, activity_id), metrics, current_lthr(session))
    return RunDetail(activity=read_activity(activity, metrics), **detail)


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


@router.get("/stats", response_model=RunStats)
def running_stats(session: SessionDep) -> RunStats:
    """Every run with its stream metrics, for the Běh → Grafy charts (E24)."""
    return run_stats(session)


@router.get("/weeks", response_model=list[PlanWeekRead])
def plan_vs_actual(
    session: SessionDep, start_date: dt.date | None = None, end_date: dt.date | None = None
) -> list[PlanWeekRead]:
    """Weekly plan from the synced knowledge base with the actual running volume of each week."""
    start = start_date or today() - dt.timedelta(days=28)
    end = end_date or start + dt.timedelta(days=12 * 7)
    weeks = session.exec(
        select(TrainingWeek)
        .where(TrainingWeek.week_end >= start, TrainingWeek.week_start <= end)
        .order_by(col(TrainingWeek.week_start))
    ).all()
    if not weeks:
        return []
    lo, _ = day_bounds(weeks[0].week_start)
    _, hi = day_bounds(weeks[-1].week_end)
    runs = session.exec(
        select(Activity)
        .where(
            col(Activity.activity_type).in_(RUN_TYPES),
            col(Activity.start_time) >= lo,
            col(Activity.start_time) < hi,
        )
        .order_by(col(Activity.start_time))
    ).all()
    days = session.exec(
        select(TrainingDay)
        .where(col(TrainingDay.planned_date).between(weeks[0].week_start, weeks[-1].week_end))
        .order_by(col(TrainingDay.planned_date))
    ).all()
    result = []
    for week in weeks:
        week_lo, _ = day_bounds(week.week_start)
        _, week_hi = day_bounds(week.week_end)
        week_runs = [r for r in runs if week_lo <= r.start_time < week_hi]
        km = [r.distance_meters / 1000 for r in week_runs]
        result.append(
            PlanWeekRead(
                **week.model_dump(),
                actual_km=round(sum(km), 1),
                actual_runs=len(week_runs),
                longest_run_km=round(max(km), 2) if km else None,
                days=[
                    PlanDayRead.model_validate(d) for d in days if week.week_start <= d.planned_date <= week.week_end
                ],
                runs=[read_activity(r) for r in week_runs],
            )
        )
    return result


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
