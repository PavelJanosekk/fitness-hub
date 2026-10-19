"""RunningCoach knowledge base: parsing and GitHub sync (fake GitHub via httpx.MockTransport)."""

import datetime as dt

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import settings
from app.main import app
from app.models.coach import AthleteProfile, CoachDocument, Race, TrainingWeek
from app.models.running import Activity
from app.routers.coach_kb import get_http
from app.services.ai_tools import ToolContext, build_coach_tools
from app.services.coach import coach_system_instruction
from app.services.coach_kb import KnowledgeBaseError, sync_knowledge_base
from app.services.kb_parser import parse_date_range, parse_days, parse_index, parse_plan

INDEX = """# Knowledge Base

**Vytvořeno:** 18.9.2026 · **Aktualizováno:** 15.10.2026 (návrat)
**Cílový závod:** Vodafone Prague Marathon, **neděle 2.5.2027**
**Generálka:** Generali Prague Half Marathon, **sobota 3.4.2027**
**Cíl:** A = **3:40–3:50**, B = sub-4:00 (jistota), 3:30 bonus; dlouhodobě
zlepšovat rychlost.

## Rychlá fakta
- LTHR = **172 bpm** (30min TT 31.8.2026), max HR ≥181
"""
PLAN = """# Timeline

## Přehled bloků
| Období | Kde | Náplň |
|---|---|---|
| 12.10.–20.12. | doma | hlavní blok |

## ⭐ Hlavní blok: 12.10.–20.12.2026

| Týden | Datum | km | LR | Kvalita | Pozn. |
|---|---|---|---|---|---|
| 1 | 12.–18.10. | ~12 | 7–8 | nic | návrat |
| 3 | 26.10.–1.11. | 32–34 (85–90 %) | 12 | strides + kopce | krevní test |
| 10 | 14.–20.12. | 55 | 22 | T + Q2 | |

## Blok: 4.–27.1.2027 (doma)
| Týden | km | LR | Kvalita |
|---|---|---|---|
| 4.–10.1. | 32–35 | 14 | strides |
| 25.–27.1. | lehce | — | odlet |

## ⭐ Maratonský blok
| Týden | Datum | km | LR | Náplň |
|---|---|---|---|---|
| 9 | 12.–18.4. | 60–65 (68 bonus) | **30 (10–12 km @ MP)** | jediný peak |

### Návrat 15.–25.10. — konkrétně
```
Čt 15.  Volno (krevní test odložen)
Pá 16.  Easy 5 km, HR ≤150
So 17.  Volno (upper jen lehce)
Ne 18.  Easy 7–8 km (podle rýmy, jinak 5–6; místo LR 12)
Út 20.  Easy 5 km + 4–6 strides (až bez rýmy)
Po 21.  Easy 7 km
Ne 25.  Long run 10 km
```
"""
CLAUDE = "# Running coach\n\nAthlete wants short, direct, evidence-based answers."
ERRATA = "# ERRATA\n\n## ❌ Kadence 163 je nízká\nOprava: 172 spm."


def test_date_ranges_roll_over_the_new_year() -> None:
    ref = dt.date(2026, 10, 15)

    assert parse_date_range("12.–18.10.", ref) == (dt.date(2026, 10, 12), dt.date(2026, 10, 18))
    assert parse_date_range("26.10.–1.11.", ref) == (dt.date(2026, 10, 26), dt.date(2026, 11, 1))
    assert parse_date_range("28.12.–3.1.", ref) == (dt.date(2026, 12, 28), dt.date(2027, 1, 3))
    assert parse_date_range("4.–10.1.", ref) == (dt.date(2027, 1, 4), dt.date(2027, 1, 10))
    assert parse_date_range("no date", ref) is None


def test_plan_tables_of_every_shape_are_parsed() -> None:
    weeks, warnings = parse_plan(PLAN, dt.date(2026, 10, 15))

    assert warnings == []
    assert [(w.week_start.isoformat(), w.km_min, w.km_max, w.long_run_km_min, w.long_run_km_max) for w in weeks] == [
        ("2026-10-12", 12, 12, 7, 8),
        ("2026-10-26", 32, 34, 12, 12),
        ("2026-12-14", 55, 55, 22, 22),
        ("2027-01-04", 32, 35, 14, 14),
        ("2027-01-25", None, None, None, None),
        ("2027-04-12", 60, 65, 30, 30),
    ]
    assert weeks[0].block == "Hlavní blok: 12.10.–20.12.2026"
    assert weeks[0].quality == "nic" and weeks[0].notes == "návrat"
    assert weeks[-1].quality == "jediný peak"


def test_day_schedule_lines_are_dated_from_the_heading_and_weekday() -> None:
    days = parse_days(PLAN, dt.date(2026, 10, 15))

    # "Po 21." is skipped: 21.10.2026 is a Wednesday, so the weekday disagrees with the date
    assert [(d.planned_date.isoformat(), d.is_rest, d.km_min, d.km_max) for d in days] == [
        ("2026-10-15", True, None, None),
        ("2026-10-16", False, 5, 5),
        ("2026-10-17", True, None, None),
        ("2026-10-18", False, 7, 8),
        ("2026-10-20", False, 5, 5),
        ("2026-10-25", False, 10, 10),
    ]
    assert days[1].text == "Easy 5 km, HR ≤150"


def test_index_gives_lthr_races_and_wrapped_goal() -> None:
    facts = parse_index(INDEX)

    assert (facts.lthr, facts.max_hr, facts.kb_updated) == (172, 181, dt.date(2026, 10, 15))
    goal_race, tune_up = facts.races
    assert (goal_race.name, goal_race.date, goal_race.distance_km, goal_race.is_goal_race) == (
        "Vodafone Prague Marathon",
        dt.date(2027, 5, 2),
        42.195,
        True,
    )
    assert goal_race.goal == "A = 3:40–3:50, B = sub-4:00 (jistota), 3:30 bonus; dlouhodobě zlepšovat rychlost."
    assert (tune_up.distance_km, tune_up.is_goal_race) == (21.0975, False)


class FakeGitHub:
    def __init__(self, files: dict[str, str], status_code: int = 200):
        self.files, self.status_code, self.raw_requests = dict(files), status_code, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            if self.status_code != 200:
                return httpx.Response(self.status_code, json={"message": "rate limited"})
            tree = [{"path": p, "type": "blob", "sha": f"sha-{hash(c)}"} for p, c in self.files.items()]
            tree.append({"path": "scripts/strava.py", "type": "blob", "sha": "x"})
            return httpx.Response(200, json={"tree": tree})
        path = request.url.path.split("/", 4)[-1]
        self.raw_requests.append(path)
        return httpx.Response(200, text=self.files[path])


@pytest.fixture(autouse=True)
def kb_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "coach_kb_repo", "someone/RunningCoach")


FILES = {"CLAUDE.md": CLAUDE, "00_INDEX.md": INDEX, "04_timeline_plan.md": PLAN, "11_errata_corrections.md": ERRATA}


def sync(session: Session, fake: FakeGitHub):
    with httpx.Client(transport=httpx.MockTransport(fake)) as http:
        return sync_knowledge_base(session, http)


def test_sync_stores_docs_and_parsed_facts(session: Session) -> None:
    result = sync(session, FakeGitHub(FILES))

    assert sorted(result.downloaded) == sorted(FILES)
    assert (result.weeks, result.races, result.lthr) == (6, 2, 172)
    assert {d.path for d in session.exec(select(CoachDocument))} == set(FILES)  # scripts/ ignored
    assert len(session.exec(select(TrainingWeek)).all()) == 6
    assert len(session.exec(select(Race)).all()) == 2
    assert session.get(AthleteProfile, 1).last_synced_at is not None


def test_resync_skips_unchanged_files_and_drops_removed_ones(session: Session) -> None:
    sync(session, FakeGitHub(FILES))
    changed = {**FILES, "00_INDEX.md": INDEX.replace("172 bpm", "175 bpm")}
    del changed["11_errata_corrections.md"]
    fake = FakeGitHub(changed)

    result = sync(session, fake)

    assert fake.raw_requests == ["00_INDEX.md"]
    assert result.removed == ["11_errata_corrections.md"]
    assert session.get(AthleteProfile, 1).lthr == 175


def test_failed_sync_is_recorded_and_keeps_old_data(session: Session) -> None:
    sync(session, FakeGitHub(FILES))

    with pytest.raises(KnowledgeBaseError):
        sync(session, FakeGitHub(FILES, status_code=403))

    assert "403" in session.get(AthleteProfile, 1).last_sync_error
    assert len(session.exec(select(CoachDocument)).all()) == 4


def test_coach_prompt_includes_core_docs_and_the_tool_reads_others(session: Session, exercises: dict[str, int]) -> None:
    sync(session, FakeGitHub(FILES))
    now = dt.datetime(2026, 10, 17, 9, 0, tzinfo=dt.UTC)

    instruction = coach_system_instruction(session, now)
    tools = {fn.__name__: fn for fn in build_coach_tools(ToolContext(session=session, now=now))}

    assert "## 11_errata_corrections.md" in instruction and "Kadence 163" in instruction
    assert "## 04_timeline_plan.md" not in instruction
    assert "read_knowledge_base: 04_timeline_plan.md" in instruction
    assert tools["read_knowledge_base"]("04")["document"] == "04_timeline_plan.md"
    context = tools["get_running_and_marathon_context"](21)
    assert context["races"][0] == {
        "name": "Generali Prague Half Marathon",
        "date": "2027-04-03",
        "days_to_go": 168,
    }
    assert context["plan_weeks"][0]["week"] == "2026-10-12..2026-10-18"


def test_weeks_endpoint_compares_plan_with_actual_runs(client: TestClient, session: Session) -> None:
    sync(session, FakeGitHub(FILES))
    for day, km in [(13, 5.0), (18, 7.5)]:
        session.add(
            Activity(
                external_id=f"strava:{day}",
                source="strava",
                start_time=dt.datetime(2026, 10, day, 7, 0, tzinfo=dt.UTC),
                activity_type="Run",
                distance_meters=km * 1000,
                duration_seconds=int(km * 360),
            )
        )
    session.commit()

    weeks = client.get("/api/running/weeks", params={"start_date": "2026-10-12", "end_date": "2026-10-18"}).json()

    assert len(weeks) == 1
    assert [r["external_id"] for r in weeks[0]["runs"]] == ["strava:13", "strava:18"]
    assert [d["planned_date"] for d in weeks[0]["days"]] == ["2026-10-15", "2026-10-16", "2026-10-17", "2026-10-18"]
    assert (weeks[0]["km_text"], weeks[0]["actual_km"], weeks[0]["actual_runs"], weeks[0]["longest_run_km"]) == (
        "~12",
        12.5,
        2,
        7.5,
    )


def test_sync_endpoint(client: TestClient) -> None:
    fake = FakeGitHub(FILES)
    http = httpx.Client(transport=httpx.MockTransport(fake))
    app.dependency_overrides[get_http] = lambda: http

    result = client.post("/api/coach/kb/sync").json()
    status = client.get("/api/coach/kb").json()

    assert result["weeks"] == 6
    assert status["lthr"] == 172 and len(status["documents"]) == 4 and status["plan_weeks"] == 6
    assert client.get("/api/coach/kb/documents/11").json()["path"] == "11_errata_corrections.md"
    http.close()


def test_races_can_be_added_and_removed_and_survive_a_resync(client: TestClient, session: Session) -> None:
    sync(session, FakeGitHub(FILES))
    races = {r["name"]: r for r in client.get("/api/coach/kb").json()["races"]}
    half = races["Generali Prague Half Marathon"]
    assert half["source"] == "kb"

    added = client.post(
        "/api/coach/races", json={"name": "  Běchovice  ", "date": "2027-09-26", "distance_km": 10}
    ).json()
    assert (added["name"], added["source"], added["is_goal_race"]) == ("Běchovice", "user", False)
    assert client.delete(f"/api/coach/races/{half['id']}").status_code == 204
    assert client.delete(f"/api/coach/races/{half['id']}").status_code == 404

    # A resync re-creates the KB races but keeps the removed one hidden and the user's race untouched
    sync(session, FakeGitHub({**FILES, "00_INDEX.md": INDEX.replace("172 bpm", "175 bpm")}))
    names = [r["name"] for r in client.get("/api/coach/kb").json()["races"]]
    assert "Generali Prague Half Marathon" not in names and "Běchovice" in names and len(names) == 2
    now = dt.datetime(2026, 10, 17, 9, tzinfo=dt.UTC)
    tools = {fn.__name__: fn for fn in build_coach_tools(ToolContext(session=session, now=now))}
    coach_races = [r["name"] for r in tools["get_running_and_marathon_context"](21)["races"]]
    assert "Generali Prague Half Marathon" not in coach_races and coach_races[-1] == "Běchovice"

    assert client.delete(f"/api/coach/races/{added['id']}").status_code == 204
    assert session.get(Race, added["id"]) is None
    assert client.post("/api/coach/races", json={"name": " ", "date": "2027-01-01"}).status_code == 422
