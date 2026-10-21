"""Data export into the private analysis repo (E40): CSV content and the GitHub commit (fake GitHub)."""

import csv
import datetime as dt
import io
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import settings
from app.main import app
from app.models.body import DailyMetric, DailySourceMetric
from app.models.export import RepoExportState
from app.models.gym import Workout, WorkoutSet
from app.models.nutrition import Food, MealLog, MealLogItem
from app.models.running import Activity, ActivityMetrics
from app.routers.export import get_http
from app.services.repo_export import (
    ExportError,
    PublicRepoError,
    build_files,
    export_due,
    export_now,
    git_blob_sha,
    push_files,
    state,
)

PRAGUE = dt.timezone(dt.timedelta(hours=2))
REPO = "owner/RunningCoach"


class FakeGitHub:
    """Just enough of the Git Data API (any repo name): one branch whose tree is a dict path -> content."""

    def __init__(self, files: dict[str, str], private: bool = True):
        self.files, self.private = dict(files), private
        self.commits: list[dict] = []
        self.head = "c0"
        self.blobs: dict[str, str] = {}
        self.trees: dict[str, dict[str, str]] = {"t0": dict(files)}
        self.commit_trees = {"c0": "t0"}
        self.ref_conflict = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = "/" + "/".join(request.url.path.split("/")[4:]) if request.url.path.count("/") > 3 else ""
        body = json.loads(request.content) if request.content else {}
        if request.method == "GET" and path == "":
            return httpx.Response(200, json={"private": self.private})
        if request.method == "GET" and path == "/git/ref/heads/master":
            return httpx.Response(200, json={"object": {"sha": self.head}})
        if request.method == "GET" and path.startswith("/git/commits/"):
            return httpx.Response(200, json={"tree": {"sha": self.commit_trees[path.rsplit("/", 1)[1]]}})
        if request.method == "GET" and path.startswith("/git/trees/"):
            tree = self.trees[path.rsplit("/", 1)[1]]
            items = [{"path": p, "type": "blob", "sha": git_blob_sha(c)} for p, c in tree.items()]
            return httpx.Response(200, json={"tree": items, "truncated": False})
        if request.method == "POST" and path == "/git/blobs":
            sha = git_blob_sha(body["content"])
            self.blobs[sha] = body["content"]
            return httpx.Response(201, json={"sha": sha})
        if request.method == "POST" and path == "/git/trees":
            tree = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                if entry["sha"] is None:
                    tree.pop(entry["path"])
                else:
                    tree[entry["path"]] = self.blobs[entry["sha"]]
            sha = f"t{len(self.trees)}"
            self.trees[sha] = tree
            return httpx.Response(201, json={"sha": sha})
        if request.method == "POST" and path == "/git/commits":
            sha = f"c{len(self.commit_trees)}"
            self.commit_trees[sha] = body["tree"]
            self.commits.append(body)
            return httpx.Response(201, json={"sha": sha})
        if request.method == "PATCH" and path == "/git/refs/heads/master":
            if self.ref_conflict:
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            self.head = body["sha"]
            self.files = self.trees[self.commit_trees[self.head]]
            return httpx.Response(200, json={})
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "export_repo", REPO)
    monkeypatch.setattr(settings, "export_branch", "master")
    monkeypatch.setattr(settings, "export_dir", "fitness-hub")
    monkeypatch.setattr(settings, "github_token", "test-token")
    monkeypatch.setattr(settings, "export_hour", 4)


def rows(files: dict[str, str], name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(files[name])))


@pytest.fixture
def data(session: Session, exercises: dict[str, int]) -> None:
    run = Activity(
        external_id="strava:1",
        source="strava",
        start_time=dt.datetime(2026, 10, 20, 7, 0, tzinfo=PRAGUE),
        activity_type="Run",
        distance_meters=10_000,
        duration_seconds=3600,
        avg_hr=150,
        rpe=4,
        description="gel 30 min",
    )
    ride = Activity(
        start_time=dt.datetime(2026, 10, 21, 18, 0, tzinfo=PRAGUE),
        activity_type="Ride",
        distance_meters=20_000,
        duration_seconds=2400,
    )
    session.add_all([run, ride])
    session.flush()
    session.add(
        ActivityMetrics(
            activity_id=run.id,
            computed_at=dt.datetime(2026, 10, 20, tzinfo=dt.UTC),
            lthr=172,
            moving_seconds=3600,
            has_heartrate=True,
            gap_s_per_km=355.4,
            ef_gap=1.234567,
            decoupling_pct=3.21,
            zone_seconds={"z1": 600, "z2": 3000, "z3": 0, "z4": 0, "z5": 0},
        )
    )
    workout = Workout(name="Push", started_at=dt.datetime(2026, 10, 21, 17, 0, tzinfo=PRAGUE))
    workout.ended_at = workout.started_at + dt.timedelta(minutes=55)
    session.add(workout)
    session.flush()
    bench = exercises["Bench Press (Barbell)"]
    session.add_all(
        [
            WorkoutSet(workout_id=workout.id, exercise_id=bench, exercise_order=1, set_order=1,
                       set_type="warmup", weight_kg=20, reps=10),
            WorkoutSet(workout_id=workout.id, exercise_id=bench, exercise_order=1, set_order=2,
                       weight_kg=40, reps=7, rpe=9),
            WorkoutSet(workout_id=workout.id, exercise_id=bench, exercise_order=1, set_order=3,
                       weight_kg=40, reps=6),
        ]
    )  # fmt: skip
    oats = Food(name_cs="Ovesné vločky", source="custom", kcal=370, protein_g=13, carbs_g=60, fat_g=7)
    session.add(oats)
    session.flush()
    breakfast = MealLog(id=uuid.uuid4(), logged_date=dt.date(2026, 10, 20), meal_type="breakfast")
    session.add(breakfast)
    session.flush()
    session.add_all(
        [
            MealLogItem(id=uuid.uuid4(), meal_log_id=breakfast.id, label="vločky", food_id=oats.id, amount_g=100),
            MealLogItem(id=uuid.uuid4(), meal_log_id=breakfast.id, label="káva", kcal=20),
        ]
    )
    session.add(DailyMetric(date=dt.date(2026, 10, 20), weight_kg=78.4, steps=12000))
    session.add(DailySourceMetric(date=dt.date(2026, 10, 20), source="samsung_health", metric="resting_hr", value=52))
    session.commit()


def test_files_keep_unknown_values_empty(session: Session, data: None) -> None:
    files = build_files(session)
    assert set(files) == {
        "README.md", "activities.csv", "gym_workouts.csv", "gym_sets.csv", "nutrition_items.csv",
        "nutrition_daily.csv", "daily_metrics.csv", "weeks.csv", "targets_daily.csv", "profile.md",
    }  # fmt: skip

    run, ride = rows(files, "activities.csv")
    assert (run["date"], run["start_local"], run["distance_km"], run["pace_s_per_km"]) == (
        "2026-10-20",
        "2026-10-20 07:00",
        "10.0",
        "360",
    )
    assert (run["gap_s_per_km"], run["ef_gap"], run["z1_min"], run["z2_min"], run["z3_min"]) == (
        "355",
        "1.235",
        "10.0",
        "50.0",
        "0.0",
    )
    assert ride["type"] == "Ride" and ride["gap_s_per_km"] == ""

    (workout,) = rows(files, "gym_workouts.csv")
    assert (workout["working_sets"], workout["volume_kg"], workout["duration_min"]) == ("2", "520", "55")
    sets = rows(files, "gym_sets.csv")
    assert [(s["set_type"], s["weight_kg"], s["reps"], s["rir"]) for s in sets] == [
        ("warmup", "20.0", "10", ""), ("normal", "40.0", "7", "1.0"), ("normal", "40.0", "6", "")
    ]  # fmt: skip

    items = rows(files, "nutrition_items.csv")
    oats = next(i for i in items if i["label"] == "vločky")
    assert (oats["kcal"], oats["protein_g"], oats["fiber_g"]) == ("370.0", "13.0", "")  # fiber unknown, not 0
    (day,) = rows(files, "nutrition_daily.csv")
    assert (day["kcal"], day["protein_g"], day["items"], day["items_missing_kcal"]) == ("390.0", "13.0", "2", "0")

    (metrics,) = rows(files, "daily_metrics.csv")
    assert (metrics["weight_kg"], metrics["steps"], metrics["sleep_hours"], metrics["resting_hr"]) == (
        "78.4",
        "12000",
        "",
        "52",
    )
    (week,) = rows(files, "weeks.csv")
    assert (week["week_start"], week["run_km"], week["runs"], week["other_cardio_min"]) == (
        "2026-10-19",
        "10.0",
        "1",
        "40",
    )
    assert (week["gym_workouts"], week["gym_working_sets"], week["avg_kcal"], week["nutrition_days"]) == (
        "1",
        "2",
        "390",
        "1",
    )


def test_push_commits_only_changes_inside_the_folder(session: Session, data: None) -> None:
    files = build_files(session)
    fake = FakeGitHub({"00_INDEX.md": "# KB", "fitness-hub/old.csv": "stale"})
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        first = push_files(http, REPO, "master", "fitness-hub", files)
        assert first.commit_sha and sorted(first.changed) == sorted(files) and first.removed == ["old.csv"]
        assert fake.files["00_INDEX.md"] == "# KB"  # the rest of the repo is untouched
        assert fake.files["fitness-hub/weeks.csv"] == files["weeks.csv"]
        assert "fitness-hub/old.csv" not in fake.files

        again = push_files(http, REPO, "master", "fitness-hub", files)
        assert again.commit_sha is None and again.changed == [] and len(fake.commits) == 1

        files["weeks.csv"] += "2026-10-26,\n"
        third = push_files(http, REPO, "master", "fitness-hub", files)
        assert third.changed == ["weeks.csv"] and len(fake.commits) == 2


def test_public_repo_needs_a_confirmation(session: Session, data: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGitHub({}, private=False)
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        with pytest.raises(PublicRepoError):
            export_now(session, http)
        assert fake.commits == []
        current = session.get(RepoExportState, 1)
        assert current is not None and "public" in (current.last_error or "") and current.last_success_at is None

        assert export_now(session, http, confirm_public=True).commit_sha  # the user confirmed in the modal
        export_now(session, http)  # later runs (the daily job) use the stored consent
        assert state(session).last_error is None

        monkeypatch.setattr(settings, "export_repo", "owner/Other")  # consent belongs to one repo only
        with pytest.raises(PublicRepoError):
            export_now(session, http)


def test_export_records_state_and_runs_once_a_day(session: Session, data: None) -> None:
    morning = dt.datetime(2026, 10, 22, 3, 30, tzinfo=PRAGUE)
    assert not export_due(session, morning)  # before EXPORT_HOUR
    assert export_due(session, morning + dt.timedelta(hours=1))

    fake = FakeGitHub({})
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        result = export_now(session, http)
    current = session.get(RepoExportState, 1)
    assert current is not None and current.last_commit_sha == result.commit_sha and current.last_error is None
    assert current.last_changed_files == 10
    assert not export_due(session, current.last_success_at + dt.timedelta(minutes=1))
    tomorrow = dt.datetime.combine(current.last_success_at.astimezone(settings.tz).date(), dt.time(5),
                                   tzinfo=settings.tz) + dt.timedelta(days=1)  # fmt: skip
    assert export_due(session, tomorrow)


def test_rejected_ref_update_is_an_error(session: Session, data: None) -> None:
    fake = FakeGitHub({})
    fake.ref_conflict = True
    with httpx.Client(transport=httpx.MockTransport(fake)) as http, pytest.raises(ExportError, match="422"):
        export_now(session, http)


def test_endpoints(client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeGitHub({})
    app.dependency_overrides[get_http] = lambda: httpx.Client(transport=httpx.MockTransport(fake))
    try:
        assert client.get("/api/export").json()["last_success_at"] is None
        response = client.post("/api/export/sync")
        assert response.status_code == 200 and response.json()["commit_sha"]
        status = client.get("/api/export").json()
        assert status["configured"] and status["repo"] == REPO and status["last_commit_sha"]

        fake.private = False
        conflict = client.post("/api/export/sync")
        assert conflict.status_code == 409 and conflict.json()["detail"] == {"code": "public_repo", "repo": REPO}
        assert client.post("/api/export/sync?confirm_public=true").status_code == 200
        assert client.get("/api/export").json()["public_ok"]
        assert client.delete("/api/export/public-consent").status_code == 204
        assert not client.get("/api/export").json()["public_ok"]
        assert client.post("/api/export/sync").status_code == 409

        monkeypatch.setattr(settings, "github_token", None)
        assert client.post("/api/export/sync").status_code == 503
    finally:
        app.dependency_overrides.pop(get_http, None)
