"""Sync the RunningCoach knowledge base from GitHub and expose it to the coach (decision E11).

The repo stays the source of truth (the user keeps editing it with Claude Code); the app keeps a read-only
copy of its root markdown files, and parses the weekly plan, races and LTHR into tables.
"""

import datetime as dt
from dataclasses import dataclass, field

import httpx
from sqlmodel import Session, delete, select

from app.config import settings
from app.models.coach import AthleteProfile, CoachDocument, Race, TrainingWeek
from app.services.kb_parser import parse_index, parse_plan
from app.timeutils import now_utc, today

GITHUB_API = "https://api.github.com"
RAW_URL = "https://raw.githubusercontent.com"
INDEX_DOC = "00_INDEX.md"
PLAN_DOC = "04_timeline_plan.md"
# Always in the coach's context; everything else is read on demand with a tool
CORE_DOCS = ("CLAUDE.md", "00_INDEX.md", "02_physiology_zones.md", "11_errata_corrections.md")
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "fitness-hub"}


class KnowledgeBaseError(Exception):
    pass


@dataclass
class KBSyncResult:
    repo: str
    downloaded: list[str] = field(default_factory=list)
    unchanged: int = 0
    removed: list[str] = field(default_factory=list)
    weeks: int = 0
    races: int = 0
    lthr: int | None = None
    warnings: list[str] = field(default_factory=list)


def profile(session: Session) -> AthleteProfile:
    return session.get(AthleteProfile, 1) or AthleteProfile(id=1)


def sync_knowledge_base(session: Session, http: httpx.Client) -> KBSyncResult:
    repo, branch = settings.coach_kb_repo, settings.coach_kb_branch
    if not repo:
        raise KnowledgeBaseError("Set COACH_KB_REPO (e.g. PavelJanosekk/RunningCoach)")
    athlete = profile(session)
    try:
        result = _sync(session, http, repo, branch)
    except (httpx.HTTPError, KnowledgeBaseError) as exc:
        session.rollback()
        athlete = profile(session)
        athlete.last_sync_error = str(exc)[:500]
        session.add(athlete)
        session.commit()
        raise KnowledgeBaseError(f"Knowledge base sync failed: {exc}") from exc
    athlete = profile(session)
    athlete.last_synced_at = now_utc()
    athlete.last_sync_error = None
    athlete.sync_warnings = result.warnings or None
    session.add(athlete)
    session.commit()
    return result


def _sync(session: Session, http: httpx.Client, repo: str, branch: str) -> KBSyncResult:
    response = http.get(f"{GITHUB_API}/repos/{repo}/git/trees/{branch}", headers=HEADERS)
    if response.status_code != 200:
        raise KnowledgeBaseError(f"GitHub tree request returned {response.status_code}")
    blobs = {
        item["path"]: item["sha"]
        for item in response.json().get("tree", [])
        if item.get("type") == "blob" and item["path"].endswith(".md") and "/" not in item["path"]
    }
    if not blobs:
        raise KnowledgeBaseError("No markdown files found in the repository root")

    result = KBSyncResult(repo=repo)
    stored = {doc.path: doc for doc in session.exec(select(CoachDocument)).all()}
    for path, sha in sorted(blobs.items()):
        doc = stored.get(path)
        if doc is not None and doc.sha == sha:
            result.unchanged += 1
            continue
        raw = http.get(f"{RAW_URL}/{repo}/{branch}/{path}", headers={"User-Agent": "fitness-hub"})
        if raw.status_code != 200:
            raise KnowledgeBaseError(f"Downloading {path} returned {raw.status_code}")
        doc = doc or CoachDocument(path=path, sha=sha, content="", fetched_at=now_utc())
        doc.sha, doc.content, doc.fetched_at = sha, raw.text, now_utc()
        session.add(doc)
        result.downloaded.append(path)
    for path, doc in stored.items():
        if path not in blobs:
            session.delete(doc)
            result.removed.append(path)
    session.flush()
    _apply_parsed_facts(session, result)
    return result


def _apply_parsed_facts(session: Session, result: KBSyncResult) -> None:
    index = session.get(CoachDocument, INDEX_DOC)
    plan = session.get(CoachDocument, PLAN_DOC)
    athlete = profile(session)
    if index is None:
        result.warnings.append(f"{INDEX_DOC} missing: LTHR and races not updated")
    else:
        facts = parse_index(index.content)
        result.warnings.extend(facts.warnings)
        athlete.lthr = facts.lthr or athlete.lthr
        athlete.max_hr = facts.max_hr or athlete.max_hr
        athlete.kb_updated = facts.kb_updated or athlete.kb_updated
        if facts.races:
            session.exec(delete(Race))
            session.add_all(Race(**vars(race)) for race in facts.races)
            result.races = len(facts.races)
    if plan is None:
        result.warnings.append(f"{PLAN_DOC} missing: weekly plan not updated")
    else:
        weeks, warnings = parse_plan(plan.content, athlete.kb_updated or today())
        result.warnings.extend(warnings)
        if weeks:  # keep the previous plan rather than wiping it when the format changed
            session.exec(delete(TrainingWeek))
            session.add_all(TrainingWeek(**vars(week)) for week in {w.week_start: w for w in weeks}.values())
            result.weeks = len(weeks)
        else:
            result.warnings.append(f"{PLAN_DOC}: no weekly plan rows recognised; previous plan kept")
    result.lthr = athlete.lthr
    session.add(athlete)
    session.flush()


def core_context(session: Session) -> str | None:
    """The always-included part of the knowledge base, or None before the first sync."""
    docs = {d.path: d for d in session.exec(select(CoachDocument)).all()}
    if not docs:
        return None
    athlete = profile(session)
    synced = athlete.last_synced_at.date().isoformat() if athlete.last_synced_at else "?"
    others = sorted(path for path in docs if path not in CORE_DOCS)
    parts = [
        f"# Znalostní báze sportovce (repo {settings.coach_kb_repo}, synchronizováno {synced})",
        "Báze je jen ke čtení a je zdrojem pravdy. Pokyny v ní o skriptech (scripts/*.py), commitech a "
        "'aktualizuj log' se tě netýkají: místo skriptů používej nástroje aplikace (data ze Stravy, "
        "metriky běhů, plán) a nic do báze nezapisuješ.",
        "Další dokumenty si načti nástrojem read_knowledge_base: " + ", ".join(others),
    ]
    parts += [f"## {path}\n\n{docs[path].content.strip()}" for path in CORE_DOCS if path in docs]
    return "\n\n".join(parts)


def read_document(session: Session, name: str) -> CoachDocument | None:
    """A document by exact path or prefix ("04" -> 04_timeline_plan.md)."""
    name = name.strip()
    if (doc := session.get(CoachDocument, name)) is not None:
        return doc
    matches = [d for d in session.exec(select(CoachDocument)).all() if d.path.startswith(name)]
    return matches[0] if len(matches) == 1 else None


def plan_weeks(session: Session, start: dt.date, end: dt.date) -> list[TrainingWeek]:
    return list(
        session.exec(
            select(TrainingWeek)
            .where(TrainingWeek.week_end >= start, TrainingWeek.week_start <= end)
            .order_by(TrainingWeek.week_start)
        ).all()
    )
