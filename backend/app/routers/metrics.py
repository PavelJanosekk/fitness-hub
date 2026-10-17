import datetime as dt

from fastapi import APIRouter, HTTPException, Query, status

from app.database import SessionDep
from app.models.body import DailyMetric
from app.schemas.body import MetricDay, MetricUpsert, WeekStats
from app.schemas.health import StepsBreakdown
from app.services.health_ingest import breakdown
from app.services.metrics import daily_series, upsert_daily_metric, weekly_stats
from app.timeutils import today

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

MAX_RANGE_DAYS = 3660


@router.get("", response_model=list[MetricDay])
def get_metrics(
    session: SessionDep, start_date: dt.date | None = None, end_date: dt.date | None = None
) -> list[MetricDay]:
    end = end_date or today()
    start = start_date or end - dt.timedelta(days=29)
    if start > end or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid date range")
    return daily_series(session, start, end)


@router.get("/weekly", response_model=list[WeekStats])
def get_weekly(session: SessionDep, weeks: int = Query(12, ge=1, le=104)) -> list[WeekStats]:
    """Weekly running km and gym sets per muscle group for the dashboard."""
    return weekly_stats(session, weeks)


@router.get("/steps-breakdown", response_model=StepsBreakdown)
def steps_breakdown(session: SessionDep, date: dt.date | None = None) -> StepsBreakdown:
    """Per-source totals, the merge method and the merged 15-min series behind a day's step count."""
    return breakdown(session, date or today())


@router.post("", response_model=DailyMetric)
def upsert_metric(body: MetricUpsert, session: SessionDep) -> DailyMetric:
    return upsert_daily_metric(session, body)
