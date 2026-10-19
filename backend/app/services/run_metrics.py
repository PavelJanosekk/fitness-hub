"""Per-run metrics from Strava per-second streams: a port of RunningCoach scripts/metrics.py (decision E12).

Grade-adjusted pace uses Minetti's energy-cost polynomial; efficiency and decoupling use the steady part of
the run (after the first 10 minutes). Zones are % of LTHR exactly as in 02_physiology_zones.md, so the numbers
follow the athlete when the LTHR changes after a retest.
"""

from dataclasses import dataclass
from typing import Any

# altitude, cadence and latlng only feed the run detail page; changing this refetches older streams
STREAM_KEYS = "time,distance,heartrate,velocity_smooth,moving,grade_smooth,altitude,cadence,latlng"
MAX_GAP_S = 10  # pauses longer than this don't count as moving time
MOVING_SPEED = 1.0  # m/s
WARMUP_S = 600
MIN_STEADY_POINTS = 120
MIN_BAND_SECONDS = 300
FLAT_COST = 3.6  # J/kg/m on the flat


def minetti(grade: float) -> float:
    """Energy cost of running (J/kg/m) at a grade given as a fraction (0.05 = 5 %), clamped to ±30 %."""
    g = max(-0.30, min(0.30, grade))
    return 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + FLAT_COST


@dataclass(frozen=True)
class Zones:
    """HR zones as % of LTHR (02_physiology_zones.md): Z1 <80 %, Z2 80-89 %, Z3 90-94 %, Z4 95-100 %, Z5 >100 %."""

    lthr: int

    @property
    def z2_low(self) -> int:
        return round(0.80 * self.lthr)

    @property
    def z2_high(self) -> int:
        return round(0.89 * self.lthr)

    @property
    def z3_high(self) -> int:
        return round(0.94 * self.lthr)

    @property
    def easy_band(self) -> tuple[int, int]:
        """The HR band used to compare aerobic efficiency over time (143-150 at LTHR 172)."""
        return round(0.83 * self.lthr), round(0.87 * self.lthr)

    def zone(self, hr: float) -> str:
        if hr < self.z2_low:
            return "z1"
        if hr <= self.z2_high:
            return "z2"
        if hr <= self.z3_high:
            return "z3"
        return "z4" if hr <= self.lthr else "z5"

    def bounds(self) -> dict[str, str]:
        return {
            "z1": f"≤{self.z2_low - 1}",
            "z2": f"{self.z2_low}-{self.z2_high}",
            "z3": f"{self.z2_high + 1}-{self.z3_high}",
            "z4": f"{self.z3_high + 1}-{self.lthr}",
            "z5": f"≥{self.lthr + 1}",
        }


def _wmean(idx: list[int], values: list[float], weights: list[float]) -> float:
    total = sum(weights[i] for i in idx)
    return sum(values[i] * weights[i] for i in idx) / total if total else 0.0


def _pace(speed: float) -> float | None:
    """Seconds per km, or None for (near) standing still."""
    return round(1000 / speed, 1) if speed and speed > 0.3 else None


def compute_metrics(streams: dict[str, Any], lthr: int | None) -> dict[str, Any] | None:
    """Metrics for one run from Strava streams (key_by_type=true); None when the streams are unusable.

    Without an LTHR the zone-based fields (zones, % above easy, easy-band GAP) stay empty.
    """

    def data(key: str) -> list[Any] | None:
        stream = streams.get(key)
        return stream.get("data") if isinstance(stream, dict) else None

    time, speed, moving_flag = data("time"), data("velocity_smooth"), data("moving")
    if not time or not speed or len(time) < 2:
        return None
    n = len(time)
    moving_flag = moving_flag or [True] * n
    grade = data("grade_smooth") or [0.0] * n
    hr = data("heartrate")
    gap = [speed[i] * minetti(grade[i] / 100) / FLAT_COST for i in range(n)]
    dts = [min(MAX_GAP_S, time[i + 1] - time[i]) for i in range(n - 1)] + [1]
    moving = [i for i in range(n) if moving_flag[i] and speed[i] > MOVING_SPEED]
    if not moving:
        return None
    first10 = [i for i in moving if time[i] < WARMUP_S]
    out: dict[str, Any] = {
        "lthr": lthr,
        "moving_seconds": int(sum(dts[i] for i in moving)),
        "pace_s_per_km": _pace(_wmean(moving, speed, dts)),
        "gap_s_per_km": _pace(_wmean(moving, gap, dts)),
        "pace_first10_s_per_km": _pace(_wmean(first10, speed, dts)) if first10 else None,
        "has_heartrate": bool(hr),
        "hr_avg_steady": None,
        "ef_gap": None,
        "decoupling_pct": None,
        "gap_at_easy_band_s_per_km": None,
        "zone_seconds": None,
        "pct_above_easy": None,
        "pct_above_steady": None,
    }
    if not hr:
        return out
    if lthr:
        zones = Zones(lthr)
        zone_seconds = dict.fromkeys(("z1", "z2", "z3", "z4", "z5"), 0.0)
        for i in moving:
            zone_seconds[zones.zone(hr[i])] += dts[i]
        total = sum(zone_seconds.values()) or 1
        out["zone_seconds"] = {k: round(v) for k, v in zone_seconds.items()}
        above_easy = zone_seconds["z3"] + zone_seconds["z4"] + zone_seconds["z5"]
        out["pct_above_easy"] = round(100 * above_easy / total, 1)
        out["pct_above_steady"] = round(100 * (zone_seconds["z4"] + zone_seconds["z5"]) / total, 1)

    steady = [i for i in moving if time[i] >= WARMUP_S]
    if len(steady) > MIN_STEADY_POINTS:
        hr_steady = _wmean(steady, hr, dts)
        out["hr_avg_steady"] = round(hr_steady, 1)
        out["ef_gap"] = round(_wmean(steady, gap, dts) * 60 / hr_steady, 3) if hr_steady else None
        half, elapsed, first, second = sum(dts[i] for i in steady) / 2, 0.0, [], []
        for i in steady:
            (first if elapsed < half else second).append(i)
            elapsed += dts[i]
        r1 = _wmean(first, gap, dts) / (_wmean(first, hr, dts) or 1)
        r2 = _wmean(second, gap, dts) / (_wmean(second, hr, dts) or 1)
        # meaningful for steady runs of ~50 min or more; stored for every run, judged by the reader
        out["decoupling_pct"] = round(100 * (r1 - r2) / r1, 1) if r1 else None
        low, high = Zones(lthr).easy_band if lthr else (0, 0)
        band = [i for i in steady if low <= hr[i] <= high]
        if lthr and sum(dts[i] for i in band) >= MIN_BAND_SECONDS:
            out["gap_at_easy_band_s_per_km"] = _pace(_wmean(band, gap, dts))
    return out


def format_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None:
        return None
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}"
