from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionDep
from app.routers import integrations, metrics, nutrition, running, webhooks, workouts
from app.services import scheduler


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    tasks = scheduler.start() if settings.scheduler_enabled else []
    yield
    await scheduler.stop(tasks)


app = FastAPI(title="Fitness Hub", lifespan=lifespan)
for module in (integrations, metrics, nutrition, running, webhooks, workouts):
    app.include_router(module.router)


@app.get("/api/health")
def health(session: SessionDep) -> JSONResponse:
    try:
        session.connection().execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok"})
