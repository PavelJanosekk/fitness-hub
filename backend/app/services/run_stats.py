"""Per-run rows behind the Běh → Grafy tab (E24); the charts aggregate them in the browser."""

import math

from sqlmodel import Session, col, select

from app.models.running import Activity, ActivityMetrics
from app.schemas.running import RunStat, RunStats
from app.services.run_analysis import RUN_TYPES, current_lthr, is_heat
from app.timeutils import local_date

VDOT_MIN_KM = 3.0
VDOT_MIN_MINUTES = 12  # Daniels' %VO2max curve is fitted for efforts of roughly 3.5 min to 4 h
VDOT_MAX_MINUTES = 240


def vdot(distance_m: float, seconds: float) -> float | None:
    """Jack Daniels' VDOT for a distance run in a time (Daniels & Gilbert oxygen-cost and %VO2max curves)."""
    minutes = seconds / 60
    if distance_m < VDOT_MIN_KM * 1000 or not VDOT_MIN_MINUTES <= minutes <= VDOT_MAX_MINUTES:
        return None
    velocity = distance_m / minutes  # m/min
    vo2 = -4.60 + 0.182258 * velocity + 0.000104 * velocity**2
    fraction = 0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)
    return round(vo2 / fraction, 1)


def run_stats(session: Session) -> RunStats:
    rows = session.exec(
        select(Activity, ActivityMetrics)
        .outerjoin(ActivityMetrics, col(ActivityMetrics.activity_id) == Activity.id)
        .where(col(Activity.activity_type).in_(RUN_TYPES), col(Activity.distance_meters) > 0)
        .order_by(col(Activity.start_time))
    ).all()
    runs = []
    for activity, metrics in rows:
        assert activity.id is not None
        runs.append(
            RunStat(
                id=activity.id,
                date=local_date(activity.start_time),
                distance_km=round(activity.distance_meters / 1000, 2),
                moving_s=activity.duration_seconds,
                avg_hr=activity.avg_hr,
                heat=is_heat(activity),
                vdot=vdot(activity.distance_meters, activity.duration_seconds),
                pace_s_per_km=round(activity.duration_seconds / (activity.distance_meters / 1000), 1),
                gap_s_per_km=metrics.gap_s_per_km if metrics else None,
                hr_avg_steady=metrics.hr_avg_steady if metrics else None,
                ef_gap=metrics.ef_gap if metrics else None,
                gap_at_easy_band_s_per_km=metrics.gap_at_easy_band_s_per_km if metrics else None,
                pct_above_easy=metrics.pct_above_easy if metrics else None,
                zone_seconds=metrics.zone_seconds if metrics else None,
            )
        )
    return RunStats(lthr=current_lthr(session), runs=runs)
