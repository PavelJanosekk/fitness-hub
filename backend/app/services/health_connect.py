"""Receiver for the Life Dashboard Companion app: Health Connect on the Android phone the watch is paired with
(and, in the same format, its iOS app for Apple Health).

Syncs are incremental: records arrive once per change, keyed by a stable uuid, plus deletions. They are stored
by uuid and every touched day is rebuilt from all stored records, so a repeated or late payload is harmless.
"""

import datetime as dt
from dataclasses import dataclass, field

from sqlmodel import Session

from app.config import settings
from app.models.body import (
    DailyMetricKind,
    DailySourceMetric,
    HealthRecord,
    HealthRecordKind,
    HealthSource,
    HealthSourceStatus,
)
from app.schemas.health import DayMerge
from app.schemas.health_connect import HCPayload
from app.services.health_ingest import rebuild_day_from_records, recompute_day
from app.timeutils import local_date, now_utc

SOURCES = {"health_connect": HealthSource.samsung_health, "healthkit_ios": HealthSource.apple_health}


@dataclass
class HealthConnectResult:
    stored: int = 0
    deleted: int = 0
    ignored: int = 0  # incomplete buckets and records without the fields we need
    days: list[DayMerge] = field(default_factory=list)


def allowed_origins() -> set[str] | None:
    """Apps whose records count; None accepts all. Avoids double counting when two apps write the same steps."""
    raw = settings.health_connect_origins.strip()
    if not raw or raw == "*":
        return None
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def ingest_health_connect(session: Session, payload: HCPayload) -> HealthConnectResult:
    result = HealthConnectResult()
    source = SOURCES.get(payload.source)
    if payload.test or source is None:  # test ping, or a Screen Time payload
        return result
    touched: set[dt.date] = set()

    def touch(start: dt.datetime, end: dt.datetime) -> None:
        day, last = local_date(start), local_date(end)
        while day <= last:
            touched.add(day)
            day += dt.timedelta(days=1)

    def store(kind: str, uuid: str, origin: str | None, start: dt.datetime, end: dt.datetime, value: float) -> None:
        if (existing := session.get(HealthRecord, (kind, uuid))) is not None:
            touch(existing.start if kind == HealthRecordKind.steps else existing.end, existing.end)  # it may have moved
        session.merge(
            HealthRecord(kind=kind, uuid=uuid, source=source, origin=origin, start=start, end=end, value=value)
        )
        touch(start if kind == HealthRecordKind.steps else end, end)  # sleep belongs to the wake-up day
        result.stored += 1

    for deleted in payload.deleted_records:
        record = session.get(HealthRecord, (deleted.type, deleted.uuid))
        if record is not None:
            touch(record.start if record.kind == HealthRecordKind.steps else record.end, record.end)
            session.delete(record)
            result.deleted += 1

    for steps in payload.steps:
        if steps.bucket_start is not None:
            # A complete bucket replaces its window; an incomplete one would have to be added up, which is
            # not idempotent, so those are skipped (keep steps at "every record" resolution in the app)
            if not steps.complete or steps.total is None:
                result.ignored += 1
                continue
            end = steps.bucket_end or steps.bucket_start
            store(
                HealthRecordKind.steps,
                f"bucket:{steps.bucket_start.isoformat()}",
                None,
                steps.bucket_start,
                end,
                steps.total,
            )
        elif steps.uuid and steps.start_time and steps.end_time and steps.count is not None:
            store(HealthRecordKind.steps, steps.uuid, steps.source, steps.start_time, steps.end_time, steps.count)
        else:
            result.ignored += 1

    for night in payload.sleep:
        if not night.uuid:
            result.ignored += 1
            continue
        start = night.session_end_time - dt.timedelta(seconds=night.duration_seconds)
        store(HealthRecordKind.sleep, night.uuid, night.source, start, night.session_end_time, night.duration_seconds)

    for total in payload.daily_totals:
        if total.steps is None:
            continue
        key = (total.date, source, DailyMetricKind.steps_total)
        existing = session.get(DailySourceMetric, key)
        newer_known = existing is not None and existing.sequence is not None and payload.sequence is not None
        if newer_known and payload.sequence < existing.sequence:
            continue  # a late payload must not overwrite a newer running total
        session.merge(
            DailySourceMetric(
                date=total.date,
                source=source,
                metric=DailyMetricKind.steps_total,
                value=total.steps,
                sequence=payload.sequence,
            )
        )
        touched.add(total.date)

    session.flush()
    origins = allowed_origins()
    for day in sorted(touched):
        rebuild_day_from_records(session, source, day, origins)
        result.days.append(recompute_day(session, day))
    if touched:
        session.merge(HealthSourceStatus(source=source, last_received_at=now_utc(), last_day=max(touched)))
    session.commit()
    return result
