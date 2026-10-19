"""Store run streams and keep their metrics current (decision E12)."""

from typing import Any

from sqlmodel import Session, col, select

from app.models.coach import AthleteProfile
from app.models.running import Activity, ActivityMetrics, ActivityStream
from app.services.run_metrics import STREAM_KEYS, compute_metrics
from app.timeutils import now_utc

RUN_TYPES = ("Run", "TrailRun", "VirtualRun")
HEAT_MARKER = "heat"  # the athlete names hot-weather runs "heat" to keep them out of efficiency trends


def current_lthr(session: Session) -> int | None:
    profile = session.get(AthleteProfile, 1)
    return profile.lthr if profile else None


def is_heat(activity: Activity) -> bool:
    return HEAT_MARKER in (activity.notes or "").casefold()


def compact_streams(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the data arrays of a key_by_type streams response."""
    return {key: {"data": value["data"]} for key, value in raw.items() if isinstance(value, dict) and "data" in value}


def store_streams(
    session: Session, activity: Activity, raw: dict[str, Any], lthr: int | None
) -> ActivityMetrics | None:
    assert activity.id is not None
    streams = compact_streams(raw)
    session.merge(ActivityStream(activity_id=activity.id, data=streams, keys=STREAM_KEYS, fetched_at=now_utc()))
    return _store_metrics(session, activity.id, streams, lthr)


def _store_metrics(
    session: Session, activity_id: int, streams: dict[str, Any], lthr: int | None
) -> ActivityMetrics | None:
    values = compute_metrics(streams, lthr)
    if values is None:
        return None
    metrics = ActivityMetrics(activity_id=activity_id, computed_at=now_utc(), **values)
    return session.merge(metrics)


def recompute_metrics(session: Session, lthr: int | None) -> int:
    """Recompute metrics whose LTHR differs (e.g. after the retest updated the knowledge base). No API calls."""
    stale = session.exec(
        select(ActivityStream)
        .outerjoin(ActivityMetrics, col(ActivityMetrics.activity_id) == ActivityStream.activity_id)
        .where(col(ActivityMetrics.activity_id).is_(None) | (col(ActivityMetrics.lthr).is_distinct_from(lthr)))
    ).all()
    for stream in stale:
        _store_metrics(session, stream.activity_id, stream.data, lthr)
    session.commit()
    return len(stale)


def streams_stale(stream: ActivityStream | None) -> bool:
    """No streams yet, or fetched before STREAM_KEYS gained keys (e.g. altitude for the run detail)."""
    return stream is None or stream.keys != STREAM_KEYS


def runs_missing_streams(session: Session, limit: int) -> list[Activity]:
    """Runs without streams first, then runs with outdated ones; newest first within each, so recent
    analysis is available before the history backfill finishes."""
    missing = col(ActivityStream.activity_id).is_(None)
    return list(
        session.exec(
            select(Activity)
            .outerjoin(ActivityStream, col(ActivityStream.activity_id) == Activity.id)
            .where(
                col(Activity.activity_type).in_(RUN_TYPES),
                col(Activity.external_id).startswith("strava:"),
                missing | col(ActivityStream.keys).is_distinct_from(STREAM_KEYS),
            )
            .order_by(missing.desc(), col(Activity.start_time).desc())
            .limit(limit)
        ).all()
    )
