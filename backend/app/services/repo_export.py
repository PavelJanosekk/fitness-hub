"""Daily export of training, nutrition and health data into the user's private analysis repo (decision E40).

The RunningCoach repo is where the user runs a stronger model with Claude Code. The app writes flat CSV files
into its own folder (EXPORT_DIR) and never touches the rest of the repo. Files are deterministic (no export
timestamp inside), so an unchanged day makes no commit. Per-second streams stay out: the repo's own
scripts/metrics.py fetches them from Strava when an analysis needs them.
"""

import csv
import datetime as dt
import hashlib
import io
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlmodel import Session, col, select

from app.config import settings
from app.models.body import DailyMetric, DailyMetricKind, DailySourceMetric
from app.models.coach import TrainingWeek
from app.models.export import RepoExportState
from app.models.gym import Exercise, Workout, WorkoutSet
from app.models.nutrition import Food, MealLog, MealLogItem, NutritionProfile
from app.models.running import Activity, ActivityMetrics
from app.services.run_analysis import RUN_TYPES
from app.timeutils import local_date, now_utc, today

GITHUB_API = "https://api.github.com"
ZONES = ("z1", "z2", "z3", "z4", "z5")  # keys of ActivityMetrics.zone_seconds


class ExportError(Exception):
    pass


class ExportNotConfiguredError(ExportError):
    pass


class PublicRepoError(ExportError):
    """The target repo is public and the user has not confirmed sharing health data into it."""


@dataclass
class ExportResult:
    repo: str
    files: int = 0
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    commit_sha: str | None = None  # None: nothing changed, no commit


def state(session: Session) -> RepoExportState:
    return session.get(RepoExportState, 1) or RepoExportState(id=1)


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "fitness-hub"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


# --- building the files ------------------------------------------------------------------------------------


def _num(value: float | None, digits: int = 1) -> float | int | None:
    if value is None:
        return None
    rounded = round(value, digits)
    return int(rounded) if digits == 0 else rounded


def _csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return out.getvalue()


def _local(moment: dt.datetime | None) -> str | None:
    return moment.astimezone(settings.tz).strftime("%Y-%m-%d %H:%M") if moment else None


def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def activities_csv(session: Session) -> str:
    rows = session.exec(
        select(Activity, ActivityMetrics)
        .outerjoin(ActivityMetrics, col(ActivityMetrics.activity_id) == Activity.id)
        .order_by(col(Activity.start_time))
    ).all()

    def row(activity: Activity, metrics: ActivityMetrics | None) -> list[Any]:
        km = activity.distance_meters / 1000
        pace = activity.duration_seconds / km if km > 0 else None
        zones = (metrics.zone_seconds or {}) if metrics else {}
        return [
            local_date(activity.start_time),
            _local(activity.start_time),
            activity.activity_type,
            activity.notes,
            _num(km, 2),
            _num(activity.duration_seconds / 60),
            _num(activity.elapsed_seconds / 60) if activity.elapsed_seconds else None,
            _num(pace, 0),
            _num(metrics.gap_s_per_km, 0) if metrics else None,
            _num(metrics.pace_first10_s_per_km, 0) if metrics else None,
            activity.avg_hr,
            activity.max_hr,
            _num(metrics.hr_avg_steady) if metrics else None,
            _num(metrics.ef_gap, 3) if metrics else None,
            _num(metrics.decoupling_pct) if metrics else None,
            _num(metrics.gap_at_easy_band_s_per_km, 0) if metrics else None,
            *(_num(zones[zone] / 60) if zone in zones else None for zone in ZONES),
            _num(metrics.pct_above_easy) if metrics else None,
            _num(metrics.pct_above_steady) if metrics else None,
            metrics.lthr if metrics else None,
            _num(activity.elevation_gain_m, 0),
            _num(activity.avg_cadence, 0),
            activity.calories,
            activity.rpe,
            activity.external_id,
            activity.description,
        ]

    return _csv(
        [
            "date", "start_local", "type", "name", "distance_km", "moving_min", "elapsed_min", "pace_s_per_km",
            "gap_s_per_km", "pace_first10_s_per_km", "avg_hr", "max_hr", "hr_steady", "ef_gap", "decoupling_pct",
            "gap_easy_band_s_per_km", *(f"{zone}_min" for zone in ZONES), "pct_above_easy",
            "pct_above_steady", "lthr_used", "elevation_gain_m", "cadence_spm", "calories", "rpe", "external_id",
            "description",
        ],
        (row(activity, metrics) for activity, metrics in rows),
    )  # fmt: skip


def gym_csvs(session: Session) -> tuple[str, str]:
    workouts = session.exec(select(Workout).order_by(col(Workout.started_at), col(Workout.id))).all()
    sets = session.exec(
        select(WorkoutSet, Exercise)
        .join(Exercise, col(Exercise.id) == WorkoutSet.exercise_id)
        .order_by(col(WorkoutSet.workout_id), col(WorkoutSet.exercise_order), col(WorkoutSet.set_order))
    ).all()
    by_workout: dict[Any, list[tuple[WorkoutSet, Exercise]]] = defaultdict(list)
    for workout_set, exercise in sets:
        by_workout[workout_set.workout_id].append((workout_set, exercise))

    workout_rows, set_rows = [], []
    for workout in workouts:
        done = [(s, e) for s, e in by_workout[workout.id] if s.completed]
        working = [(s, e) for s, e in done if s.set_type != "warmup"]
        volume = sum((s.weight_kg or 0) * (s.reps or 0) for s, _ in working)
        minutes = (workout.ended_at - workout.started_at).total_seconds() / 60 if workout.ended_at else None
        workout_rows.append([
            local_date(workout.started_at), _local(workout.started_at), _local(workout.ended_at), _num(minutes, 0),
            workout.ended_by, workout.name, workout.source, len(working), len({e.id for _, e in working}),
            _num(volume, 0), workout.notes, workout.id,
        ])  # fmt: skip
        for workout_set, exercise in by_workout[workout.id]:
            rir = 10 - workout_set.rpe if workout_set.rpe is not None else None
            set_rows.append([
                local_date(workout.started_at), workout.name, exercise.name, exercise.muscle_group,
                workout_set.exercise_order, workout_set.set_order, workout_set.set_type, workout_set.weight_kg,
                workout_set.reps, workout_set.duration_s, workout_set.distance_m, _num(rir), workout_set.completed,
                workout_set.planned_weight_kg, workout_set.planned_reps, workout_set.role, workout_set.unusual,
                workout_set.notes, workout.id,
            ])  # fmt: skip

    workouts_text = _csv(
        ["date", "start_local", "end_local", "duration_min", "ended_by", "name", "source", "working_sets",
         "exercises", "volume_kg", "notes", "workout_id"],
        workout_rows,
    )  # fmt: skip
    sets_text = _csv(
        ["date", "workout", "exercise", "muscle_group", "exercise_order", "set_order", "set_type", "weight_kg",
         "reps", "duration_s", "distance_m", "rir", "completed", "planned_weight_kg", "planned_reps", "role",
         "unusual", "notes", "workout_id"],
        set_rows,
    )  # fmt: skip
    return workouts_text, sets_text


def nutrition_csvs(session: Session) -> tuple[str, str, dict[dt.date, dict[str, Any]]]:
    """Item-level log plus daily totals. A missing macro stays empty and is counted, never treated as 0."""
    rows = session.exec(
        select(MealLog, MealLogItem, Food)
        .join(MealLogItem, col(MealLogItem.meal_log_id) == MealLog.id)
        .outerjoin(Food, col(Food.id) == MealLogItem.food_id)
        .order_by(col(MealLog.logged_date), col(MealLog.created_at), col(MealLogItem.label), col(MealLogItem.id))
    ).all()
    item_rows = []
    days: dict[dt.date, dict[str, Any]] = {}
    for meal, item, food in rows:
        values = {}
        for column in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g"):
            manual = getattr(item, column, None)
            if manual is None and food is not None and item.amount_g is not None:
                per_100 = getattr(food, column)
                manual = per_100 * item.amount_g / 100 if per_100 is not None else None
            values[column] = manual
        item_rows.append([
            meal.logged_date, meal.meal_type, item.label, (food.name_cs or food.name_en) if food else None,
            _num(item.amount_g, 0), *(_num(v) for v in values.values()), food.source if food else "quick_add",
        ])  # fmt: skip
        day = days.setdefault(meal.logged_date, {"items": 0, "missing_kcal": 0, "meals": set()} | {
            column: None for column in values
        })  # fmt: skip
        day["items"] += 1
        day["meals"].add(meal.meal_type)
        if values["kcal"] is None:
            day["missing_kcal"] += 1
        for column, value in values.items():
            if value is not None:
                day[column] = (day[column] or 0) + value

    items_text = _csv(
        ["date", "meal", "label", "food", "amount_g", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g",
         "sugar_g", "food_source"],
        item_rows,
    )  # fmt: skip
    daily_text = _csv(
        ["date", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "items", "items_missing_kcal",
         "meals_logged"],
        (
            [day, *(_num(d[c]) for c in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g")),
             d["items"], d["missing_kcal"], len(d["meals"])]
            for day, d in sorted(days.items())
        ),
    )  # fmt: skip
    return items_text, daily_text, days


def daily_metrics_csv(session: Session) -> tuple[str, dict[dt.date, DailyMetric]]:
    """Merged daily values plus resting HR (lowest across sources); days without any value are absent."""
    resting: dict[dt.date, float] = {}
    for metric in session.exec(
        select(DailySourceMetric).where(DailySourceMetric.metric == DailyMetricKind.resting_hr)
    ).all():
        resting[metric.date] = min(resting.get(metric.date, metric.value), metric.value)
    metrics = {m.date: m for m in session.exec(select(DailyMetric)).all()}
    rows = []
    for day in sorted(set(metrics) | set(resting)):
        m = metrics.get(day)
        values = [m.weight_kg, m.steps, m.sleep_hours, m.calories_out] if m else [None] * 4
        if all(v is None for v in values) and day not in resting:
            continue
        rows.append([day, *values, _num(resting.get(day), 0), m.notes if m else None])
    header = ["date", "weight_kg", "steps", "sleep_hours", "calories_out", "resting_hr", "notes"]
    return _csv(header, rows), metrics


def weeks_csv(
    session: Session,
    activities: Sequence[Activity],
    intake: dict[dt.date, dict[str, Any]],
    body: dict[dt.date, DailyMetric],
) -> str:
    """Monday-Sunday overview: plan vs actual running, gym, average intake, weight and steps."""
    weeks: dict[dt.date, dict[str, Any]] = defaultdict(lambda: defaultdict(float))
    for activity in activities:
        week = weeks[_week_start(local_date(activity.start_time))]
        if activity.activity_type in RUN_TYPES:
            km = activity.distance_meters / 1000
            week["run_km"] += km
            week["runs"] += 1
            week["long_run_km"] = max(week["long_run_km"], km)
        else:
            week["other_cardio_min"] += activity.duration_seconds / 60
    for started_at in session.exec(
        select(Workout.started_at)
        .join(WorkoutSet, col(WorkoutSet.workout_id) == Workout.id)
        .where(col(WorkoutSet.completed), WorkoutSet.set_type != "warmup")
    ).all():
        weeks[_week_start(local_date(started_at))]["gym_sets"] += 1
    for started_at in session.exec(select(Workout.started_at)).all():
        weeks[_week_start(local_date(started_at))]["gym_workouts"] += 1
    daily = [(day, "kcal", d["kcal"]) for day, d in intake.items()]
    daily += [(day, "protein", d["protein_g"]) for day, d in intake.items()]
    daily += [(day, "weight", m.weight_kg) for day, m in body.items()]
    daily += [(day, "steps", m.steps) for day, m in body.items()]
    for day, key, value in daily:
        if value is not None:
            week = weeks[_week_start(day)]
            week[f"{key}_sum"] += value
            week[f"{key}_days"] += 1
    plan = {w.week_start: w for w in session.exec(select(TrainingWeek)).all()}

    def avg(week: dict[str, Any], key: str, digits: int) -> float | int | None:
        return _num(week[f"{key}_sum"] / week[f"{key}_days"], digits) if week.get(f"{key}_days") else None

    rows = []
    for start in sorted(set(weeks) | {s for s in plan if s <= today()}):
        week, planned = weeks[start], plan.get(start)
        rows.append([
            start, start.isocalendar()[0] * 100 + start.isocalendar()[1], _num(week["run_km"]), int(week["runs"]),
            _num(week["long_run_km"]), planned.km_text if planned else None, planned.long_run_text if planned else None,
            planned.quality if planned else None, _num(week["other_cardio_min"], 0), int(week["gym_workouts"]),
            int(week["gym_sets"]), avg(week, "kcal", 0), avg(week, "protein", 0), int(week.get("kcal_days", 0)),
            avg(week, "weight", 1), avg(week, "steps", 0),
        ])  # fmt: skip
    return _csv(
        ["week_start", "iso_week", "run_km", "runs", "long_run_km", "plan_km", "plan_long_run", "plan_quality",
         "other_cardio_min", "gym_workouts", "gym_working_sets", "avg_kcal", "avg_protein_g", "nutrition_days",
         "avg_weight_kg", "avg_steps"],
        rows,
    )  # fmt: skip


def profile_md(session: Session) -> str:
    targets = session.get(NutritionProfile, 1)
    lines = ["# Profil a cíle (z aplikace Fitness Hub)", ""]
    if targets is None:
        return "\n".join([*lines, "Nutriční cíle nejsou nastavené.", ""])
    for label, value, unit in (
        ("Pohlaví", targets.sex, ""),
        ("Rok narození", targets.birth_year, ""),
        ("Výška", targets.height_cm, " cm"),
        ("Cíl kcal", targets.kcal_target, " kcal"),
        ("Cíl kcal v tréninkový den", targets.kcal_target_training_day, " kcal"),
        ("Cíl bílkovin", targets.protein_target_g, " g"),
        ("Cíl sacharidů", targets.carbs_target_g, " g"),
        ("Cíl tuků", targets.fat_target_g, " g"),
        ("Cíl vlákniny", targets.fiber_target_g, " g"),
    ):
        lines.append(f"- {label}: {value}{unit}" if value is not None else f"- {label}: neznámé")
    return "\n".join([*lines, ""])


README = """# Data z aplikace Fitness Hub

Tuhle složku generuje aplikace Fitness Hub každý den (a na tlačítko v Nastavení). **Neupravuj ji ručně** —
další export ji přepíše. Zdrojem pravdy je databáze aplikace; tady je čitelná kopie pro hlubší analýzu.

Pravidla:
- Prázdná buňka = neznámá hodnota, **ne nula**. Den, který v souboru chybí, nemá žádná data.
- Data a časy jsou v místním čase (Europe/Prague). Týdny jsou pondělí–neděle.
- Sekundové streamy běhů tu nejsou — na ně použij `scripts/metrics.py` (Strava API).

Soubory:
- `activities.csv` — všechny aktivity ze Stravy (běh, kolo, plavání, …), jedna na řádek. Tempa v s/km
  (`gap` = tempo upravené o převýšení, Minetti). `ef_gap` = GAP m/min na úder, `decoupling_pct` = GAP/HR první
  vs. druhá polovina ustálené části, `z1_min`–`z5_min` = minuty v zónách podle `lthr_used`. Metriky jen u běhů
  se streamem; `description` je popis ze Stravy (fueling, bolest 0–10).
- `gym_workouts.csv` — tréninky v posilovně; `volume_kg` = váha × opakování pracovních sérií.
- `gym_sets.csv` — každá série. `rir` = opakování v záloze (prázdné = nepotvrzeno), `planned_*`/`role` = plán
  progrese, `unusual` = série mimo progresi. Váha 0 = vlastní váha.
- `nutrition_items.csv` — každá položka jídelníčku s gramy a makry.
- `nutrition_daily.csv` — denní součty; `items_missing_kcal` = položky bez známých kcal (součet je pak podhodnocený).
- `daily_metrics.csv` — váha, kroky, spánek, klidový tep po dnech.
- `weeks.csv` — týdenní přehled: běh vs. plán z `04_timeline_plan.md`, posilovna, průměrný příjem (jen přes
  dny se záznamem, počet v `nutrition_days`), průměrná váha a kroky.
- `profile.md` — nutriční cíle a základní údaje.
"""


def build_files(session: Session) -> dict[str, str]:
    activities = session.exec(select(Activity).order_by(col(Activity.start_time))).all()
    workouts_text, sets_text = gym_csvs(session)
    items_text, daily_nutrition, intake = nutrition_csvs(session)
    metrics_text, body = daily_metrics_csv(session)
    return {
        "README.md": README,
        "activities.csv": activities_csv(session),
        "gym_workouts.csv": workouts_text,
        "gym_sets.csv": sets_text,
        "nutrition_items.csv": items_text,
        "nutrition_daily.csv": daily_nutrition,
        "daily_metrics.csv": metrics_text,
        "weeks.csv": weeks_csv(session, activities, intake, body),
        "profile.md": profile_md(session),
    }


# --- writing to GitHub -------------------------------------------------------------------------------------


def git_blob_sha(text: str) -> str:
    """The sha GitHub reports for a file with this content, so unchanged files are not rewritten."""
    data = text.encode()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _call(http: httpx.Client, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
    response = http.request(method, url, headers=github_headers(), json=body)
    if response.status_code >= 300:
        raise ExportError(f"GitHub {method} {url.removeprefix(GITHUB_API)} returned {response.status_code}")
    return response.json()


def push_files(
    http: httpx.Client, repo: str, branch: str, folder: str, files: dict[str, str], allow_public: bool = False
) -> ExportResult:
    """One commit replacing the folder's content with `files`; no commit when nothing changed."""
    base = f"{GITHUB_API}/repos/{repo}"
    info = _call(http, "GET", base)
    if not info.get("private") and not allow_public:
        # Weight, food and health data go into a public repo only after an explicit confirmation
        raise PublicRepoError(f"{repo} is public: confirm sharing health data into it first")
    head = _call(http, "GET", f"{base}/git/ref/heads/{branch}")["object"]["sha"]
    base_tree = _call(http, "GET", f"{base}/git/commits/{head}")["tree"]["sha"]
    tree = _call(http, "GET", f"{base}/git/trees/{base_tree}?recursive=1")
    if tree.get("truncated"):
        raise ExportError("Repository tree too large to compare")
    prefix = folder.strip("/") + "/"
    existing = {
        item["path"]: item["sha"]
        for item in tree.get("tree", [])
        if item.get("type") == "blob" and item["path"].startswith(prefix)
    }

    result = ExportResult(repo=repo, files=len(files))
    entries: list[dict[str, Any]] = []
    for name, text in sorted(files.items()):
        path = prefix + name
        if existing.get(path) == git_blob_sha(text):
            continue
        blob = _call(http, "POST", f"{base}/git/blobs", {"content": text, "encoding": "utf-8"})
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        result.changed.append(name)
    for path in sorted(existing):  # the folder belongs to the export: files it no longer writes go away
        if path.removeprefix(prefix) not in files:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            result.removed.append(path.removeprefix(prefix))
    if not entries:
        return result

    new_tree = _call(http, "POST", f"{base}/git/trees", {"base_tree": base_tree, "tree": entries})
    message = f"data: Fitness Hub export {today().isoformat()}\n\nChanged: {', '.join(result.changed) or '-'}"
    if result.removed:
        message += f"\nRemoved: {', '.join(result.removed)}"
    commit = _call(
        http, "POST", f"{base}/git/commits", {"message": message, "tree": new_tree["sha"], "parents": [head]}
    )
    # Not forced: if the user pushed in the meantime GitHub refuses (422) and the next run starts from their commit
    _call(http, "PATCH", f"{base}/git/refs/heads/{branch}", {"sha": commit["sha"]})
    result.commit_sha = commit["sha"]
    return result


def export_now(session: Session, http: httpx.Client, confirm_public: bool = False) -> ExportResult:
    """`confirm_public` records the user's consent to export into this repo even though it is public."""
    repo = settings.export_repo
    if not repo or not settings.github_token:
        raise ExportNotConfiguredError("Set EXPORT_REPO and GITHUB_TOKEN")
    current = state(session)
    if confirm_public:
        current.public_ok_repo = repo
    current.last_run_at = now_utc()
    files = build_files(session)
    try:
        result = push_files(
            http, repo, settings.export_branch, settings.export_dir, files, allow_public=current.public_ok_repo == repo
        )
    except (httpx.HTTPError, ExportError) as exc:
        session.rollback()
        current = state(session)
        current.last_run_at = now_utc()
        current.last_error = str(exc)[:500]
        session.add(current)
        session.commit()
        if isinstance(exc, PublicRepoError):
            raise
        raise ExportError(f"Export failed: {exc}") from exc
    current.last_success_at = current.last_run_at
    current.last_error = None
    if result.commit_sha:
        current.last_commit_sha = result.commit_sha
        current.last_changed_files = len(result.changed) + len(result.removed)
    session.add(current)
    session.commit()
    return result


def export_due(session: Session, now: dt.datetime | None = None) -> bool:
    """Once a day after EXPORT_HOUR (local); a failed day is retried by the next hourly check."""
    now = now or now_utc()
    if now.astimezone(settings.tz).hour < settings.export_hour:
        return False
    last = state(session).last_success_at
    return last is None or local_date(last) < local_date(now)
