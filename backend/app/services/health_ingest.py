"""Health data ingestion and multi-source merge (docs/SPEC.md §6.5, decisions E7/E8).

Steps from the iPhone and the watch overlap whenever both are carried. Interval data is spread over
15-minute buckets; per bucket the higher source wins, and the day is the sum of those maxima. Without
interval data the day falls back to the highest daily total. A manual value always wins.

Records longer than an hour carry no usable timing (Samsung Health writes one whole-day record), so they
only count toward their source's daily total (steps_untimed), never into the buckets (E38).
"""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from sqlmodel import Session, col, delete, select

from app.models.body import (
    DailyMetric,
    DailyMetricKind,
    DailySourceMetric,
    HealthRecord,
    HealthRecordKind,
    HealthSource,
    HealthSourceStatus,
    StepBucket,
)
from app.schemas.health import BucketRow, DayMerge, HealthPush, StepsBreakdown
from app.timeutils import day_bounds, local_date, now_utc

BUCKET = dt.timedelta(minutes=15)
UNTIMED_AFTER = dt.timedelta(hours=1)
SLEEP_SOURCE_PRIORITY = (HealthSource.manual, HealthSource.samsung_health, HealthSource.apple_health)


def floor_bucket(moment: dt.datetime) -> dt.datetime:
    moment = moment.astimezone(dt.UTC)
    return moment.replace(minute=moment.minute - moment.minute % 15, second=0, microsecond=0)


def distribute(
    start: dt.datetime, end: dt.datetime, count: float, lo: dt.datetime, hi: dt.datetime
) -> dict[dt.datetime, float]:
    """Spread a sample over 15-min buckets in proportion to time overlap, keeping only the part in [lo, hi)."""
    if end <= start:  # instantaneous sample
        return {floor_bucket(start): count} if lo <= start < hi else {}
    clipped_start, clipped_end = max(start, lo), min(end, hi)
    total_seconds = (end - start).total_seconds()
    buckets: dict[dt.datetime, float] = {}
    bucket = floor_bucket(clipped_start)
    while bucket < clipped_end:
        overlap = (min(bucket + BUCKET, clipped_end) - max(bucket, clipped_start)).total_seconds()
        if overlap > 0:
            buckets[bucket] = buckets.get(bucket, 0.0) + count * overlap / total_seconds
        bucket += BUCKET
    return buckets


def split_steps(
    samples: Iterable[tuple[dt.datetime, dt.datetime, float]], lo: dt.datetime, hi: dt.datetime
) -> tuple[dict[dt.datetime, float], float]:
    """The part of each sample inside [lo, hi): timed ones spread over buckets, longer ones summed as untimed."""
    buckets: dict[dt.datetime, float] = defaultdict(float)
    untimed = 0.0
    for start, end, count in samples:
        parts = distribute(start, end, count, lo, hi)
        if end - start > UNTIMED_AFTER:
            untimed += sum(parts.values())
        else:
            for bucket, steps in parts.items():
                buckets[bucket] += steps
    return buckets, untimed


def _store_steps(
    session: Session, source: str, day: dt.date, buckets: dict[dt.datetime, float], untimed: float
) -> None:
    session.add_all(StepBucket(source=source, bucket_start=b, steps=v) for b, v in buckets.items())
    key = (day, source, DailyMetricKind.steps_untimed)
    if untimed > 0:
        session.merge(DailySourceMetric(date=day, source=source, metric=DailyMetricKind.steps_untimed, value=untimed))
    elif (stale := session.get(DailySourceMetric, key)) is not None:
        session.delete(stale)


def _merged_minutes(sessions: list[tuple[dt.datetime, dt.datetime]]) -> float:
    """Total minutes covered by (start, end) sessions; overlapping duplicates (e.g. two apps) count once."""
    total, current_start, current_end = 0.0, None, None
    for start, end in sorted(sessions):
        if current_end is None or start > current_end:
            if current_end is not None:
                total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += (current_end - current_start).total_seconds()
    return total / 60


def ingest(session: Session, push: HealthPush) -> list[DayMerge]:
    days = sorted(set(push.days))
    for day in days:
        lo, hi = day_bounds(day)
        session.exec(
            delete(StepBucket).where(
                StepBucket.source == push.source, col(StepBucket.bucket_start) >= lo, col(StepBucket.bucket_start) < hi
            )
        )
        session.exec(
            delete(DailySourceMetric).where(DailySourceMetric.date == day, DailySourceMetric.source == push.source)
        )

        buckets, untimed = split_steps(((s.start, s.end, s.count) for s in push.steps), lo, hi)
        _store_steps(session, push.source, day, buckets, untimed)

        for value in push.daily:
            if value.date == day and value.metric != DailyMetricKind.steps_untimed:
                session.merge(DailySourceMetric(date=day, source=push.source, metric=value.metric, value=value.value))

        night = [s for s in push.sleep_sessions if local_date(s.end) == day]
        if night:
            session.merge(
                DailySourceMetric(
                    date=day,
                    source=push.source,
                    metric=DailyMetricKind.sleep_minutes,
                    value=round(_merged_minutes([(n.start, n.end) for n in night]), 1),
                )
            )
    session.merge(HealthSourceStatus(source=push.source, last_received_at=now_utc(), last_day=days[-1]))
    session.flush()
    results = [recompute_day(session, day) for day in days]
    session.commit()
    return results


def rebuild_day_from_records(session: Session, source: str, day: dt.date, origins: set[str] | None) -> None:
    """Recreate a source's step buckets and sleep minutes for a day from its stored raw records.

    `origins` limits which writing apps count (None = all); records without an origin (buckets) always count.
    """
    lo, hi = day_bounds(day)

    def counts(record: HealthRecord) -> bool:
        return origins is None or record.origin is None or record.origin in origins

    session.exec(
        delete(StepBucket).where(
            StepBucket.source == source, col(StepBucket.bucket_start) >= lo, col(StepBucket.bucket_start) < hi
        )
    )
    step_records = session.exec(
        select(HealthRecord).where(
            HealthRecord.source == source,
            HealthRecord.kind == HealthRecordKind.steps,
            col(HealthRecord.start) < hi,
            col(HealthRecord.end) >= lo,
        )
    ).all()
    buckets, untimed = split_steps(((r.start, r.end, r.value) for r in step_records if counts(r)), lo, hi)
    _store_steps(session, source, day, buckets, untimed)

    nights = session.exec(
        select(HealthRecord).where(
            HealthRecord.source == source,
            HealthRecord.kind == HealthRecordKind.sleep,
            col(HealthRecord.end) >= lo,
            col(HealthRecord.end) < hi,
        )
    ).all()
    sleep_key = (day, source, DailyMetricKind.sleep_minutes)
    intervals = [(r.start, r.end) for r in nights if counts(r)]
    if intervals:
        minutes = round(_merged_minutes(intervals), 1)
        session.merge(DailySourceMetric(date=day, source=source, metric=DailyMetricKind.sleep_minutes, value=minutes))
    elif (stale := session.get(DailySourceMetric, sleep_key)) is not None:
        session.delete(stale)
    session.flush()


def _day_inputs(
    session: Session, day: dt.date
) -> tuple[dict[str, dict[dt.datetime, float]], dict[tuple[str, str], float]]:
    lo, hi = day_bounds(day)
    per_source: dict[str, dict[dt.datetime, float]] = defaultdict(dict)
    for b in session.exec(
        select(StepBucket).where(col(StepBucket.bucket_start) >= lo, col(StepBucket.bucket_start) < hi)
    ):
        per_source[b.source][b.bucket_start] = b.steps
    daily = {
        (m.source, m.metric): m.value
        for m in session.exec(select(DailySourceMetric).where(DailySourceMetric.date == day))
    }
    return per_source, daily


def _merge_steps(
    per_source: dict[str, dict[dt.datetime, float]], daily: dict[tuple[str, str], float]
) -> tuple[float | None, str | None, dict[str, float]]:
    totals = {src: sum(b.values()) for src, b in per_source.items()}
    for (src, metric), value in daily.items():
        if metric == DailyMetricKind.steps_untimed:
            totals[src] = totals.get(src, 0.0) + value
    for (src, metric), value in daily.items():
        if metric == DailyMetricKind.steps_total and src != HealthSource.manual:
            totals[src] = value  # a device's own daily total beats a possibly incomplete interval sum
    manual = daily.get((HealthSource.manual, DailyMetricKind.steps_total))
    if manual is not None:
        return manual, "manual", totals
    if len(per_source) >= 2:
        starts = set().union(*(b.keys() for b in per_source.values()))
        bucket_total = sum(max(b.get(start, 0.0) for b in per_source.values()) for start in starts)
        return max(bucket_total, *totals.values()), "buckets", totals
    if totals:
        return max(totals.values()), "max_daily" if len(totals) > 1 else "single_source", totals
    return None, None, totals


def _merge_sleep(daily: dict[tuple[str, str], float]) -> float | None:
    for source in SLEEP_SOURCE_PRIORITY:
        minutes = daily.get((source, DailyMetricKind.sleep_minutes))
        if minutes is not None:
            return round(minutes / 60, 2)
    return None


def recompute_day(session: Session, day: dt.date) -> DayMerge:
    """Recompute the merged steps and sleep for a day and store them on DailyMetric."""
    per_source, daily = _day_inputs(session, day)
    steps, method, _ = _merge_steps(per_source, daily)
    sleep_hours = _merge_sleep(daily)
    metric = session.get(DailyMetric, day)
    if metric is None and (steps is not None or sleep_hours is not None):
        metric = DailyMetric(date=day)
    if metric is not None:
        metric.steps = round(steps) if steps is not None else None
        metric.sleep_hours = sleep_hours
        session.add(metric)
    return DayMerge(
        date=day, steps=round(steps) if steps is not None else None, steps_method=method, sleep_hours=sleep_hours
    )


def breakdown(session: Session, day: dt.date) -> StepsBreakdown:
    per_source, daily = _day_inputs(session, day)
    steps, method, totals = _merge_steps(per_source, daily)
    starts = sorted(set().union(*(b.keys() for b in per_source.values()))) if per_source else []
    rows = [
        BucketRow(
            start=start,
            merged=round(max(b.get(start, 0.0) for b in per_source.values()), 1),
            per_source={src: round(b[start], 1) for src, b in per_source.items() if start in b},
        )
        for start in starts
    ]
    return StepsBreakdown(
        date=day,
        steps=round(steps) if steps is not None else None,
        steps_method=method,
        sleep_hours=_merge_sleep(daily),
        source_totals={src: round(v) for src, v in totals.items()},
        buckets=rows,
    )
