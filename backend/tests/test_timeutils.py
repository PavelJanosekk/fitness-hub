from datetime import UTC, date, datetime, timedelta

import pytest

from app.timeutils import day_bounds, local_date, today


def test_today_uses_prague_date_after_local_midnight() -> None:
    # 22:30 UTC on 17 Oct is 00:30 on 18 Oct in Prague (CEST, UTC+2)
    assert today(datetime(2026, 10, 17, 22, 30, tzinfo=UTC)) == date(2026, 10, 18)


def test_today_in_winter_time() -> None:
    # 23:30 UTC on 1 Dec is 00:30 on 2 Dec in Prague (CET, UTC+1)
    assert today(datetime(2026, 12, 1, 23, 30, tzinfo=UTC)) == date(2026, 12, 2)


def test_local_date_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="naive"):
        local_date(datetime(2026, 10, 17, 12, 0))  # noqa: DTZ001  (naive on purpose)


def test_day_bounds_regular_day() -> None:
    start, end = day_bounds(date(2026, 10, 17))

    assert start == datetime(2026, 10, 16, 22, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=24)


@pytest.mark.parametrize(
    ("day", "length"),
    [
        (date(2026, 3, 29), timedelta(hours=23)),  # spring forward
        (date(2026, 10, 25), timedelta(hours=25)),  # fall back
    ],
)
def test_day_bounds_dst_switch_days(day: date, length: timedelta) -> None:
    start, end = day_bounds(day)

    assert end - start == length
