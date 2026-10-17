import datetime as dt

from fastapi import APIRouter, HTTPException, status

from app.database import SessionDep
from app.models.body import DailyMetric, DailyMetricKind, DailySourceMetric, HealthSource
from app.schemas.body import MetricDay, MetricUpsert
from app.services.metrics import daily_series
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


@router.post("", response_model=DailyMetric)
def upsert_metric(body: MetricUpsert, session: SessionDep) -> DailyMetric:
    day = body.date or today()
    metric = session.get(DailyMetric, day) or DailyMetric(date=day)
    for field, value in body.model_dump(exclude={"date"}).items():
        if value is not None:
            setattr(metric, field, value)
    # Manual steps/sleep are kept as their own source so device merges never overwrite them
    manual = {DailyMetricKind.steps_total: body.steps, DailyMetricKind.sleep_minutes: body.sleep_hours}
    for kind, value in manual.items():
        if value is not None:
            stored = value * 60 if kind == DailyMetricKind.sleep_minutes else value
            session.merge(DailySourceMetric(date=day, source=HealthSource.manual, metric=kind, value=stored))
    session.add(metric)
    session.commit()
    session.refresh(metric)
    return metric
