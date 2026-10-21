"""Daily kcal and macro targets from the running plan (decision E41).

target = base + Σ k·weight·km (runs of the day except the long run) + ½ of today's long run + ½ of tomorrow's
planned long run, rounded to 50 kcal (half up). Protein and fat are fixed in the profile; carbs are the rest.
The plan is the parsed day lines of 04_timeline_plan.md (`training_days`); Strava runs of the day replace the
planned km in order. Every day is computed on demand (nothing is frozen).

Base, protein, fat and the maintenance offset are the user's settings (NutritionProfile); the rules below are
generic and stay constants.
"""

import datetime as dt
import math
import re
import statistics
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.models.body import DailyMetric, DailyMetricKind, DailySourceMetric
from app.models.coach import TrainingDay
from app.models.nutrition import NutritionProfile
from app.models.running import Activity
from app.services.run_analysis import RUN_TYPES
from app.timeutils import day_bounds, today


class Mode(StrEnum):
    cut = "cut"
    maintenance = "maintenance"
    off = "off"  # no target, intake is only logged


class RunKind(StrEnum):
    easy = "easy"
    strides = "strides"
    hills = "hills"
    threshold = "threshold"
    long_run = "long_run"


# The mode calendar: each entry applies from its date until the next one (days before the first: off)
MODES: tuple[tuple[dt.date, Mode], ...] = (
    (dt.date(2026, 10, 21), Mode.cut),
    (dt.date(2026, 12, 21), Mode.maintenance),
    (dt.date(2027, 1, 4), Mode.cut),
    (dt.date(2027, 1, 28), Mode.off),
    (dt.date(2027, 2, 15), Mode.maintenance),
)
K_FACTOR = {
    RunKind.easy: 0.75,
    RunKind.strides: 0.75,
    RunKind.hills: 0.75,
    RunKind.threshold: 1.0,
    RunKind.long_run: 1.0,
}
ROUND_KCAL = 50
WEIGHT_WINDOW_DAYS = 7
DEFAULT_MAINTENANCE_OFFSET = 500

# Monday proposals for the base (cut mode only)
PROPOSALS_FROM = dt.date(2026, 11, 9)
MIN_READINGS = 3  # per window, for both the weight trend and resting HR
FAST_LOSS_KG_WEEK = 0.6
SLOW_LOSS_KG_WEEK = 0.2
RAISE_FAST_LOSS = 150
LOWER_SLOW_LOSS = 100
MIN_BASE = 1900
RHR_MARGIN_BPM = 5
RAISE_HIGH_RHR = 200

KIND_LABELS = {
    RunKind.easy: "easy",
    RunKind.strides: "strides",
    RunKind.hills: "kopce",
    RunKind.threshold: "threshold",
    RunKind.long_run: "LR",
}
_LONG_RUN = re.compile(r"\blong\s*run\b|\blr\b")
_THRESHOLD = re.compile(r"\bthreshold\b|\btempo\b|(?:^|[\s+(])t\s*\d|(?:^|[\s+(])t(?:$|[\s+)])")
_HILLS = re.compile(r"\bkopc|\bhills?\b")
_STRIDES = re.compile(r"\bstrides\b|\brovinky\b")


def round_half_up(value: float, step: float = 1) -> int:
    return int(math.floor(value / step + 0.5) * step)


def mode_for(day: dt.date) -> Mode:
    current = Mode.off
    for start, mode in MODES:
        if day >= start:
            current = mode
    return current


def classify(text: str) -> RunKind:
    """Run type of a plan line. Only LR and threshold change the formula; everything else counts as easy."""
    lowered = text.casefold().replace("✅", " ")
    if _LONG_RUN.search(lowered):
        return RunKind.long_run
    if _THRESHOLD.search(lowered):
        return RunKind.threshold
    if _HILLS.search(lowered):
        return RunKind.hills
    if _STRIDES.search(lowered):
        return RunKind.strides
    return RunKind.easy


@dataclass
class Run:
    kind: RunKind
    km: float
    source: str  # "plan" | "strava"


def planned_runs(session: Session, day: dt.date) -> list[Run]:
    """The day's plan line as a run (the midpoint of a km range); rest days and lines without km plan nothing."""
    line = session.get(TrainingDay, day)
    if line is None or line.is_rest or line.km_min is None:
        return []
    km = (line.km_min + (line.km_max or line.km_min)) / 2
    return [Run(classify(line.text), round(km, 2), "plan")]


def day_runs(session: Session, day: dt.date) -> list[Run]:
    """Strava runs replace the planned ones in order and keep their planned type; extra runs count as easy."""
    plan = planned_runs(session, day)
    lo, hi = day_bounds(day)
    actual = session.exec(
        select(Activity)
        .where(
            col(Activity.activity_type).in_(RUN_TYPES), col(Activity.start_time) >= lo, col(Activity.start_time) < hi
        )
        .order_by(col(Activity.start_time))
    ).all()
    runs = [
        Run(plan[i].kind if i < len(plan) else RunKind.easy, round(activity.distance_meters / 1000, 2), "strava")
        for i, activity in enumerate(actual)
    ]
    return runs + plan[len(actual) :]


def weight_used(session: Session, day: dt.date) -> float | None:
    """Mean of the weigh-ins of the last 7 days including `day`; else the last known weight before it."""
    start = day - dt.timedelta(days=WEIGHT_WINDOW_DAYS - 1)
    window = session.exec(
        select(DailyMetric.weight_kg).where(
            col(DailyMetric.date).between(start, day), col(DailyMetric.weight_kg).is_not(None)
        )
    ).all()
    if window:
        return round(statistics.fmean(w for w in window if w is not None), 2)
    return session.exec(
        select(DailyMetric.weight_kg)
        .where(col(DailyMetric.date) < start, col(DailyMetric.weight_kg).is_not(None))
        .order_by(col(DailyMetric.date).desc())
    ).first()


class TargetPart(BaseModel):
    label: str  # "easy 7 km", "½ LR 10 km", "½ LR zítra 10 km"
    key: str  # export label: "easy", "long_run", "long_run_tomorrow"
    km: float
    kcal: float
    source: str  # plan | strava


class DayTarget(BaseModel):
    date: dt.date
    mode: Mode
    base_kcal: float | None  # None in off mode or without a base in the profile
    weight_used_kg: float | None
    parts: list[TargetPart] = []
    extra_kcal: float = 0
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbs_g: float | None = None

    @property
    def runs_text(self) -> str:
        return ";".join(f"{p.key}:{p.km:.1f}" for p in self.parts)


def _km_text(km: float) -> str:
    return f"{km:g}".replace(".", ",")


def day_target(session: Session, day: dt.date, profile: NutritionProfile | None = None) -> DayTarget:
    profile = profile or session.get(NutritionProfile, 1)
    mode = mode_for(day)
    weight = weight_used(session, day)
    base = profile.kcal_target if profile else None
    if mode == Mode.maintenance and base is not None:
        offset = profile.maintenance_offset_kcal if profile and profile.maintenance_offset_kcal is not None else None
        base += DEFAULT_MAINTENANCE_OFFSET if offset is None else offset
    if mode == Mode.off or base is None:
        return DayTarget(date=day, mode=mode, base_kcal=None if mode == Mode.off else base, weight_used_kg=weight)

    parts: list[TargetPart] = []
    if weight is not None:
        for run in day_runs(session, day):
            share = 0.5 if run.kind == RunKind.long_run else 1
            label = f"{'½ ' if share < 1 else ''}{KIND_LABELS[run.kind]} {_km_text(run.km)} km"
            kcal = share * K_FACTOR[run.kind] * weight * run.km
            parts.append(TargetPart(label=label, key=run.kind.value, km=run.km, kcal=round(kcal, 1), source=run.source))
        for run in planned_runs(session, day + dt.timedelta(days=1)):
            if run.kind == RunKind.long_run:
                kcal = 0.5 * K_FACTOR[run.kind] * weight * run.km
                parts.append(
                    TargetPart(
                        label=f"½ LR zítra {_km_text(run.km)} km",
                        key="long_run_tomorrow",
                        km=run.km,
                        kcal=round(kcal, 1),
                        source="plan",
                    )
                )
    extra = sum(p.kcal for p in parts)
    kcal = round_half_up(base + extra, ROUND_KCAL)
    protein = profile.protein_target_g if profile else None
    fat = profile.fat_target_g if profile else None
    carbs = None
    if protein is not None and fat is not None:
        carbs = round_half_up((kcal - protein * 4 - fat * 9) / 4)
    return DayTarget(
        date=day,
        mode=mode,
        base_kcal=base,
        weight_used_kg=weight,
        parts=parts,
        extra_kcal=round(extra, 1),
        kcal=kcal,
        protein_g=protein,
        fat_g=fat,
        carbs_g=carbs,
    )


# --- Monday proposal for the base ----------------------------------------------------------------------------


@dataclass
class Proposal:
    monday: dt.date
    current_base: float
    new_base: float
    reason: str  # Czech, shown in the app
    details: dict[str, float] = field(default_factory=dict)


def _mean_in(values: dict[dt.date, float], start: dt.date, end: dt.date) -> tuple[float | None, int]:
    window = [v for d, v in values.items() if start <= d <= end]
    return (statistics.fmean(window), len(window)) if window else (None, 0)


def _resting_hr(session: Session, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """The lowest resting HR per day across sources (manual entry or a device)."""
    per_day: dict[dt.date, float] = {}
    for metric in session.exec(
        select(DailySourceMetric).where(
            DailySourceMetric.metric == DailyMetricKind.resting_hr, col(DailySourceMetric.date).between(start, end)
        )
    ).all():
        per_day[metric.date] = min(per_day.get(metric.date, metric.value), metric.value)
    return per_day


def base_proposal(session: Session, day: dt.date | None = None) -> Proposal | None:
    """This week's suggestion (computed for its Monday), or None: nothing to change, too few readings, already
    accepted or dismissed, before PROPOSALS_FROM, or not in cut mode."""
    day = day or today()
    monday = day - dt.timedelta(days=day.weekday())
    profile = session.get(NutritionProfile, 1)
    if monday < PROPOSALS_FROM or mode_for(monday) != Mode.cut or profile is None or profile.kcal_target is None:
        return None
    if profile.base_proposal_handled_on == monday:
        return None
    base = profile.kcal_target

    hr = _resting_hr(session, monday - dt.timedelta(days=34), monday)
    recent_hr, recent_n = _mean_in(hr, monday - dt.timedelta(days=6), monday)
    earlier = [v for d, v in hr.items() if d <= monday - dt.timedelta(days=7)]
    if recent_hr is not None and recent_n >= MIN_READINGS and len(earlier) >= MIN_READINGS:
        median = statistics.median(earlier)
        if recent_hr >= median + RHR_MARGIN_BPM:
            return Proposal(
                monday,
                base,
                base + RAISE_HIGH_RHR,
                f"Klidový tep {recent_hr:.0f} je o {recent_hr - median:.0f} bpm nad mediánem posledních 4 týdnů "
                f"({median:.0f}): málo jídla nebo únava.",
                {"rhr_7d": round(recent_hr, 1), "rhr_median_28d": median},
            )

    weights = {
        m.date: m.weight_kg
        for m in session.exec(
            select(DailyMetric).where(
                col(DailyMetric.date).between(monday - dt.timedelta(days=20), monday),
                col(DailyMetric.weight_kg).is_not(None),
            )
        ).all()
        if m.weight_kg is not None
    }
    now, now_n = _mean_in(weights, monday - dt.timedelta(days=6), monday)
    before, before_n = _mean_in(weights, monday - dt.timedelta(days=20), monday - dt.timedelta(days=14))
    if now is None or before is None or now_n < MIN_READINGS or before_n < MIN_READINGS:
        return None
    rate = (now - before) / 2  # kg per week, negative = losing
    details = {"rate_kg_week": round(rate, 2), "weight_7d": round(now, 2), "weight_7d_two_weeks_ago": round(before, 2)}
    if rate < -FAST_LOSS_KG_WEEK:
        reason = f"Hubneš {-rate:.2f} kg/týden, rychleji než {FAST_LOSS_KG_WEEK} kg/týden."
        return Proposal(monday, base, base + RAISE_FAST_LOSS, reason, details)
    if rate > -SLOW_LOSS_KG_WEEK:
        new_base = max(MIN_BASE, base - LOWER_SLOW_LOSS)
        if new_base >= base:
            return None
        trend = f"hubneš jen {-rate:.2f} kg/týden" if rate < 0 else f"váha {'stojí' if rate == 0 else 'roste'}"
        reason = f"Za 2 týdny {trend}, pomaleji než {SLOW_LOSS_KG_WEEK} kg/týden."
        return Proposal(monday, base, new_base, reason, details)
    return None


def handle_proposal(session: Session, accept: bool, day: dt.date | None = None) -> Proposal | None:
    """Accept (the base changes) or dismiss this week's proposal; either way it is not shown again this week."""
    proposal = base_proposal(session, day)
    profile = session.get(NutritionProfile, 1)
    if proposal is None or profile is None:
        return None
    if accept:
        profile.kcal_target = proposal.new_base
    profile.base_proposal_handled_on = proposal.monday
    session.add(profile)
    session.commit()
    return proposal
