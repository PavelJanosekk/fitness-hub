"""Periodic background jobs, started from the FastAPI lifespan.

A few asyncio loops instead of a scheduler library: two jobs don't need cron syntax or persistence.
Requires a single Uvicorn worker, otherwise every worker would run the jobs.
"""

import asyncio
import datetime as dt
import logging
from collections.abc import Callable

import httpx
from sqlmodel import Session

from app.database import engine
from app.services.strava_client import StravaNotConfiguredError, StravaNotConnectedError, sync_activities
from app.services.workouts import auto_finish_stale

log = logging.getLogger(__name__)

AUTO_FINISH_EVERY = dt.timedelta(minutes=10)
STRAVA_SYNC_EVERY = dt.timedelta(minutes=30)


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
    ]


async def stop(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
