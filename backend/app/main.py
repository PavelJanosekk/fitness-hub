from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.config import settings
from app.database import SessionDep, engine
from app.routers import ai_coach, coach_kb, integrations, metrics, nutrition, running, webhooks, workouts
from app.services import scheduler
from app.services.nutrition import kt_import
from app.spa import mount_spa


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    tasks = scheduler.start() if settings.scheduler_enabled else []
    if settings.scheduler_enabled:
        resume_kt_import()
    yield
    await scheduler.stop(tasks)


def resume_kt_import() -> None:
    """A KT import interrupted by a restart or deploy continues from its cursor."""
    with Session(engine) as session:
        running = kt_import.get_state(session).status == "running"
    if running and settings.kaloricketabulky_email and settings.kaloricketabulky_password:
        nutrition.start_kt_import()


app = FastAPI(title="Fitness Hub", lifespan=lifespan)
for module in (ai_coach, coach_kb, integrations, metrics, nutrition, running, webhooks, workouts):
    app.include_router(module.router)


@app.get("/api/health")
def health(session: SessionDep) -> JSONResponse:
    try:
        session.connection().execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok"})


# Last, so the catch-all for client-side routes never shadows an API route
if settings.static_dir and Path(settings.static_dir).is_dir():
    mount_spa(app, Path(settings.static_dir))
