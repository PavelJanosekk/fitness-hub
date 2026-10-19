"""The run detail page: chart series, per-km splits and the route from the stored Strava streams."""

from typing import Any

from app.models.running import Activity, ActivityMetrics, ActivityStream
from app.services.run_analysis import RUN_TYPES, streams_stale
from app.services.run_metrics import FLAT_COST, MAX_GAP_S, MOVING_SPEED, Zones, minetti

MAX_POINTS = 400  # chart points sent to the phone
MAX_ROUTE_POINTS = 800
MIN_LAST_SPLIT_M = 100  # a shorter remainder after the last full km is dropped
STOPPED_SPEED = 0.8  # m/s: slower counts as standing, no pace shown
ELEVATION_NOISE_M = 2.0  # hysteresis for the computed elevation gain (GPS/barometer jitter)


def _data(streams: dict[str, Any], key: str) -> list[Any] | None:
    stream = streams.get(key)
    values = stream.get("data") if isinstance(stream, dict) else None
    return values or None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _r(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def elevation_gain(altitude: list[float]) -> float:
    """Climb with a small hysteresis, so jitter on flat ground doesn't add up."""
    gain, ref = 0.0, altitude[0]
    for value in altitude[1:]:
        if value - ref >= ELEVATION_NOISE_M:
            gain += value - ref
            ref = value
        elif value < ref:
            ref = value
    return round(gain)


def _series(streams: dict[str, Any], run: bool) -> dict[str, list[float | None]]:
    """Column-oriented chart series, averaged into at most MAX_POINTS buckets."""
    time = _data(streams, "time") or []
    n = len(time)
    speed = _data(streams, "velocity_smooth")
    grade = _data(streams, "grade_smooth")
    distance = _data(streams, "distance")
    hr = _data(streams, "heartrate")
    altitude = _data(streams, "altitude")
    cadence = _data(streams, "cadence")
    latlng = _data(streams, "latlng")
    step = max(1, -(-n // MAX_POINTS))
    out: dict[str, list[float | None]] = {
        key: []
        for key, present in (
            ("time_s", True),
            ("distance_km", distance),
            ("pace", speed),
            ("gap", speed),
            ("hr", hr),
            ("altitude", altitude),
            ("cadence", cadence),
            ("lat", latlng),
            ("lng", latlng),
        )
        if present
    }
    for lo in range(0, n, step):
        idx = range(lo, min(n, lo + step))
        last = idx[-1]
        out["time_s"].append(time[last])
        if distance:
            out["distance_km"].append(round(distance[last] / 1000, 3))
        if speed:
            moving = [i for i in idx if speed[i] >= STOPPED_SPEED]
            v = _mean([speed[i] for i in moving])
            out["pace"].append(round(1000 / v) if v else None)
            g = _mean([speed[i] * minetti((grade[i] if grade else 0) / 100) / FLAT_COST for i in moving])
            out["gap"].append(round(1000 / g) if g else None)
        if hr:
            out["hr"].append(_r(_mean([hr[i] for i in idx if hr[i]]), 0))
        if altitude:
            out["altitude"].append(_r(_mean([altitude[i] for i in idx])))
        if cadence:
            # Strava counts a run's cadence per leg
            spm = _mean([cadence[i] * (2 if run else 1) for i in idx if cadence[i]])
            out["cadence"].append(_r(spm, 0))
        if latlng:
            out["lat"].append(latlng[last][0])
            out["lng"].append(latlng[last][1])
    return out


def _splits(streams: dict[str, Any], run: bool) -> list[dict[str, Any]]:
    """Per-km splits on moving time, like Strava: pace, GAP, HR, elevation change, cadence."""
    time, distance, speed = _data(streams, "time"), _data(streams, "distance"), _data(streams, "velocity_smooth")
    if not time or not distance or not speed or len(time) < 2:
        return []
    grade, hr = _data(streams, "grade_smooth"), _data(streams, "heartrate")
    altitude, cadence, moving_flag = _data(streams, "altitude"), _data(streams, "cadence"), _data(streams, "moving")
    n = len(time)
    splits: list[dict[str, Any]] = []

    def close(points: list[int], start_m: float, end_m: float) -> None:
        # the intervals between the split's points; its boundary points are shared with the neighbours
        dts = {i: min(MAX_GAP_S, time[i + 1] - time[i]) for i in points[:-1]}
        moving = [i for i in points[:-1] if (moving_flag[i] if moving_flag else True) and speed[i] > MOVING_SPEED]
        moving_s = sum(dts[i] for i in moving)
        km = (end_m - start_m) / 1000
        if not moving or km <= 0:
            return
        gap_speed = sum(speed[i] * minetti((grade[i] if grade else 0) / 100) / FLAT_COST * dts[i] for i in moving)
        with_hr = [i for i in moving if hr and hr[i]]
        with_cadence = [i for i in moving if cadence and cadence[i]]
        splits.append(
            {
                "km": round(km, 2),
                "moving_s": round(moving_s),
                "pace": round(moving_s / km),
                "gap": round(1000 * moving_s / gap_speed) if gap_speed else None,
                "hr": round(sum(hr[i] * dts[i] for i in with_hr) / sum(dts[i] for i in with_hr)) if with_hr else None,
                "elevation_m": round(altitude[points[-1]] - altitude[points[0]]) if altitude else None,
                "cadence": round(sum(cadence[i] for i in with_cadence) / len(with_cadence) * (2 if run else 1))
                if with_cadence
                else None,
            }
        )

    points: list[int] = []
    start_m, boundary = 0.0, 1000.0
    for i in range(n):
        points.append(i)
        if distance[i] >= boundary:
            close(points, start_m, distance[i])
            start_m, boundary, points = distance[i], boundary + 1000, [i]
    if distance[-1] - start_m >= MIN_LAST_SPLIT_M:
        close(points, start_m, distance[-1])
    return splits


def _route(streams: dict[str, Any]) -> list[list[float]]:
    latlng = _data(streams, "latlng") or []
    step = max(1, -(-len(latlng) // MAX_ROUTE_POINTS))
    route = latlng[::step]
    if latlng and route[-1] != latlng[-1]:
        route.append(latlng[-1])
    return [[round(lat, 5), round(lng, 5)] for lat, lng in route]


def run_detail(
    activity: Activity, stream: ActivityStream | None, metrics: ActivityMetrics | None, lthr: int | None
) -> dict[str, Any]:
    streams = stream.data if stream else {}
    run = activity.activity_type in RUN_TYPES
    altitude = _data(streams, "altitude")
    zone_lthr = metrics.lthr if metrics and metrics.lthr else lthr
    return {
        "streams": "none" if stream is None else "partial" if streams_stale(stream) else "full",
        "elevation_gain_m": activity.elevation_gain_m
        if activity.elevation_gain_m is not None
        else elevation_gain(altitude)
        if altitude
        else None,
        "lthr": zone_lthr,
        "zone_bounds": Zones(zone_lthr).bounds() if zone_lthr else None,
        "zone_seconds": metrics.zone_seconds if metrics else None,
        "hr_avg_steady": metrics.hr_avg_steady if metrics else None,
        "pace_first10_s_per_km": metrics.pace_first10_s_per_km if metrics else None,
        "series": _series(streams, run) if _data(streams, "time") else {},
        "splits": _splits(streams, run),
        "route": _route(streams),
    }
