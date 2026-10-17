from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionDep

app = FastAPI(title="Fitness Hub")


@app.get("/api/health")
def health(session: SessionDep) -> JSONResponse:
    try:
        session.connection().execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok"})
