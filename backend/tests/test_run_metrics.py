"""Port of RunningCoach scripts/metrics.py, checked on synthetic per-second streams."""

import datetime as dt

import pytest
from sqlmodel import Session

from app.models.coach import AthleteProfile
from app.models.running import Activity, ActivityMetrics
from app.services.ai_tools import ToolContext, build_coach_tools
from app.services.run_analysis import recompute_metrics, store_streams
from app.services.run_metrics import Zones, compute_metrics, format_pace, minetti

NOW = dt.datetime(2026, 10, 17, 9, 0, tzinfo=dt.UTC)


def streams(seconds: int, speed: float, hr, grade: float = 0.0) -> dict:
    """Constant speed/grade; hr is a number or a function of the second."""
    heart = [hr(t) if callable(hr) else hr for t in range(seconds)]
    return {
        "time": {"data": list(range(seconds))},
        "velocity_smooth": {"data": [speed] * seconds},
        "heartrate": {"data": heart},
        "moving": {"data": [True] * seconds},
        "grade_smooth": {"data": [grade] * seconds},
    }


def test_zones_match_the_knowledge_base_table_at_lthr_172() -> None:
    assert Zones(172).bounds() == {"z1": "≤137", "z2": "138-153", "z3": "154-162", "z4": "163-172", "z5": "≥173"}
    assert Zones(172).easy_band == (143, 150)


def test_minetti_is_flat_cost_on_the_flat_and_higher_uphill() -> None:
    assert minetti(0) == pytest.approx(3.6)
    assert minetti(0.10) == pytest.approx(5.968, abs=0.001)
    assert minetti(0.5) == minetti(0.30)  # clamped


def test_flat_steady_run() -> None:
    metrics = compute_metrics(streams(2400, 3.0, 145), lthr=172)

    assert format_pace(metrics["pace_s_per_km"]) == "5:33"
    assert metrics["gap_s_per_km"] == metrics["pace_s_per_km"]
    assert metrics["ef_gap"] == pytest.approx(180 / 145, abs=0.001)
    assert metrics["decoupling_pct"] == 0
    assert metrics["zone_seconds"]["z2"] == 2400
    assert metrics["pct_above_easy"] == 0
    assert format_pace(metrics["gap_at_easy_band_s_per_km"]) == "5:33"


def test_uphill_gap_is_faster_than_pace() -> None:
    metrics = compute_metrics(streams(1200, 2.0, 150, grade=10.0), lthr=172)

    assert format_pace(metrics["pace_s_per_km"]) == "8:20"
    assert format_pace(metrics["gap_s_per_km"]) == "5:02"


def test_cardiac_drift_shows_as_positive_decoupling_and_threshold_time_counts() -> None:
    # HR 145 in the first steady half, 165 (Z4) in the second
    metrics = compute_metrics(streams(3000, 3.0, lambda t: 145 if t < 1800 else 165), lthr=172)

    assert metrics["decoupling_pct"] > 5
    assert metrics["zone_seconds"]["z4"] == 1200
    assert metrics["pct_above_steady"] == 40.0


def test_without_lthr_only_zone_fields_are_empty() -> None:
    metrics = compute_metrics(streams(2400, 3.0, 145), lthr=None)

    assert metrics["ef_gap"] is not None
    assert metrics["zone_seconds"] is None and metrics["gap_at_easy_band_s_per_km"] is None


def run(session: Session, day: int, name: str = "Easy") -> Activity:
    activity = Activity(
        external_id=f"strava:{day}",
        source="strava",
        start_time=dt.datetime(2026, 10, day, 6, 0, tzinfo=dt.UTC),
        activity_type="Run",
        distance_meters=8000,
        duration_seconds=2400,
        notes=name,
    )
    session.add(activity)
    session.flush()
    return activity


def test_metrics_are_recomputed_when_lthr_changes(session: Session) -> None:
    activity = run(session, 10)
    store_streams(session, activity, streams(2400, 3.0, 156), lthr=172)  # Z3 at 172
    session.commit()

    assert recompute_metrics(session, 172) == 0
    assert recompute_metrics(session, 180) == 1  # after a retest: 156 is now Z2
    metrics = session.get(ActivityMetrics, activity.id)
    assert metrics.lthr == 180 and metrics.zone_seconds["z2"] == 2400


def test_efficiency_trend_compares_easy_runs_and_excludes_heat_and_quality(session: Session) -> None:
    session.add(AthleteProfile(id=1, lthr=172))
    store_streams(session, run(session, 8), streams(2400, 3.0, 146), 172)
    store_streams(session, run(session, 10, "Morning run heat"), streams(2400, 2.5, 148), 172)
    store_streams(session, run(session, 12, "Threshold"), streams(2400, 3.4, lambda t: 145 if t < 900 else 166), 172)
    store_streams(session, run(session, 14), streams(2400, 3.1, 147), 172)
    session.commit()
    tools = {fn.__name__: fn for fn in build_coach_tools(ToolContext(session=session, now=NOW))}

    trend = tools["get_efficiency_trend"](8)

    assert trend["easy_band_hr"] == "143-150"
    assert [(r["date"], r["gap_at_easy_band"]) for r in trend["runs"]] == [
        ("2026-10-08", "5:33"),
        ("2026-10-14", "5:23"),
    ]
    assert trend["excluded"] == {"heat": 1, "quality": 1, "no_easy_band": 0}
    assert trend["months"]["2026-10"]["runs"] == 2
