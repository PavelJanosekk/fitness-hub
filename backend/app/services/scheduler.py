"""Periodic background jobs, started from the FastAPI lifespan.

A few asyncio loops instead of a scheduler library: these jobs don't need cron syntax or persistence.
Requires a single Uvicorn worker, otherwise every worker would run the jobs.
"""

import asyncio
import datetime as dt
import logging
from collections.abc import Callable

import httpx
from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.services.coach_kb import KnowledgeBaseError, sync_knowledge_base
from app.services.gemini_service import AINotConfiguredError, get_client
from app.services.nutrition import mapper
from app.services.repo_export import ExportError, export_due, export_now
from app.services.strava_client import StravaNotConfiguredError, StravaNotConnectedError, sync_activities
from app.services.workouts import auto_finish_stale

log = logging.getLogger(__name__)

AUTO_FINISH_EVERY = dt.timedelta(minutes=10)
STRAVA_SYNC_EVERY = dt.timedelta(minutes=30)
KB_SYNC_EVERY = dt.timedelta(hours=6)
MICROS_MAPPER_EVERY = dt.timedelta(minutes=20)
EXPORT_CHECK_EVERY = dt.timedelta(hours=1)


def auto_finish_job() -> None:
    with Session(engine) as session:
        if closed := auto_finish_stale(session):
            log.info("auto-finished %d idle workout(s)", closed)


def strava_sync_job() -> None:
    with Session(engine) as session, httpx.Client(timeout=20) as http:
        try:
            result = sync_activities(session, http)
        except (StravaNotConfiguredError, StravaNotConnectedError):
            return  # nothing to do until the user connects Strava
        log.info("strava sync: %s", result)


def kb_sync_job() -> None:
    if not settings.coach_kb_repo:
        return
    with Session(engine) as session, httpx.Client(timeout=20) as http:
        try:
            result = sync_knowledge_base(session, http)
        except KnowledgeBaseError as exc:
            log.warning("%s", exc)
            return
        if result.downloaded or result.removed:
            log.info("knowledge base: %s", result)


def micros_mapper_job() -> None:
    """New foods (KT import, OFF, web estimates, custom) get their USDA micronutrient references (E26)."""
    try:
        client = get_client()
    except AINotConfiguredError:
        return
    with Session(engine) as session:
        if mapped := mapper.run(session, client):
            log.info("micros mapper: %d food(s) mapped", mapped)


def repo_export_job() -> None:
    """The daily data export into the analysis repo (E40); checked hourly, runs once a day."""
    if not settings.export_repo or not settings.github_token:
        return
    with Session(engine) as session, httpx.Client(timeout=60) as http:
        if not export_due(session):
            return
        try:
            result = export_now(session, http)
        except ExportError as exc:
            log.warning("%s", exc)
            return
        log.info("repo export: %s", result)


async def _every(interval: dt.timedelta, job: Callable[[], None], first_delay: dt.timedelta) -> None:
    await asyncio.sleep(first_delay.total_seconds())
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:
            log.exception("background job %s failed", job.__name__)
        await asyncio.sleep(interval.total_seconds())


def start() -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(_every(AUTO_FINISH_EVERY, auto_finish_job, first_delay=dt.timedelta(seconds=5))),
        asyncio.create_task(_every(STRAVA_SYNC_EVERY, strava_sync_job, first_delay=dt.timedelta(minutes=1))),
        asyncio.create_task(_every(KB_SYNC_EVERY, kb_sync_job, first_delay=dt.timedelta(seconds=20))),
        asyncio.create_task(_every(MICROS_MAPPER_EVERY, micros_mapper_job, first_delay=dt.timedelta(minutes=2))),
        asyncio.create_task(_every(EXPORT_CHECK_EVERY, repo_export_job, first_delay=dt.timedelta(minutes=5))),
    ]


async def stop(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
