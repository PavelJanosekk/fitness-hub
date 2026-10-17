import datetime as dt
from statistics import fmean

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models.body import DailyMetric
from app.models.nutrition import MealLog, MealLogItem
from app.schemas.body import MetricDay

ROLLING_DAYS = 7


def intake_by_day(session: Session, start: dt.date, end: dt.date) -> dict[dt.date, tuple[float, ...]]:
    """(kcal, protein, carbs, fat) per day that has meal logs. Days without logs are absent, not zero."""
    rows = session.exec(
        select(
            MealLog.logged_date,
            func.sum(MealLogItem.kcal),
            func.sum(MealLogItem.protein_g),
            func.sum(MealLogItem.carbs_g),
            func.sum(MealLogItem.fat_g),
        )
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .where(col(MealLog.logged_date).between(start, end))
        .group_by(col(MealLog.logged_date))
    ).all()
    return {day: (kcal, protein, carbs, fat) for day, kcal, protein, carbs, fat in rows}


def daily_series(session: Session, start: dt.date, end: dt.date) -> list[MetricDay]:
    """One entry per day in [start, end] with 7-day rolling averages over the days that have data."""
    window_start = start - dt.timedelta(days=ROLLING_DAYS - 1)
    metrics = {
        m.date: m for m in session.exec(select(DailyMetric).where(col(DailyMetric.date).between(window_start, end)))
    }
    intake = intake_by_day(session, window_start, end)

    def rolling(day: dt.date, value_of) -> float | None:
        values = [v for offset in range(ROLLING_DAYS) if (v := value_of(day - dt.timedelta(days=offset))) is not None]
        return round(fmean(values), 2) if values else None

    def weight(day: dt.date) -> float | None:
        return metrics[day].weight_kg if day in metrics else None

    def kcal(day: dt.date) -> float | None:
        return intake[day][0] if day in intake else None

    series = []
    for offset in range((end - start).days + 1):
        day = start + dt.timedelta(days=offset)
        metric = metrics.get(day)
        kcal_in, protein, carbs, fat = intake.get(day, (None, None, None, None))
        series.append(
            MetricDay(
                date=day,
                weight_kg=weight(day),
                weight_7d_avg=rolling(day, weight),
                calories_in=kcal_in,
                calories_in_7d_avg=rolling(day, kcal),
                protein_g=protein,
                carbs_g=carbs,
                fat_g=fat,
                calories_out=metric.calories_out if metric else None,
                steps=metric.steps if metric else None,
                sleep_hours=metric.sleep_hours if metric else None,
                notes=metric.notes if metric else None,
            )
        )
    return series
