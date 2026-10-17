"""The single place that decides "now", "today" and day boundaries.

Timestamps are stored in UTC; calendar days are always days in APP_TZ (docs/SPEC.md §3),
so a meal logged at 00:30 in Prague lands on the right date even though the container runs in UTC.
"""

from datetime import UTC, date, datetime, time, timedelta

from app.config import settings


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_date(moment: datetime) -> date:
    """Calendar date of an aware datetime in APP_TZ."""
    if moment.tzinfo is None:
        raise ValueError("naive datetime: localize it before asking for its date")
    return moment.astimezone(settings.tz).date()


def today(now: datetime | None = None) -> date:
    return local_date(now or now_utc())


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a local calendar day as UTC datetimes; 23 h or 25 h long on DST switch days."""
    start = datetime.combine(day, time.min, tzinfo=settings.tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=settings.tz)
    return start.astimezone(UTC), end.astimezone(UTC)
