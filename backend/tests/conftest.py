"""Test fixtures: a dedicated <db>_test database migrated to head, one rolled-back transaction per test."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parent.parent
_app_url = make_url(settings.database_url)
TEST_DB_URL = _app_url.set(database=f"{_app_url.database}_test")


def _ensure_test_database() -> None:
    admin = create_engine(_app_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_URL.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _ensure_test_database()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.render_as_string(hide_password=False).replace("%", "%%"))
    command.upgrade(cfg, "head")
    test_engine = create_engine(TEST_DB_URL)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    # Commits inside the code under test become savepoints; the outer transaction is always rolled back
    with engine.connect() as conn:
        outer = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db_session:
            yield db_session
        outer.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
