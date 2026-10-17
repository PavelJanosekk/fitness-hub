import pytest

from app.config import normalize_database_url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@db:5432/fitness_db",
        "postgres://u:p@db:5432/fitness_db",
        "postgresql+psycopg2://u:p@db:5432/fitness_db",
        "postgresql+psycopg://u:p@db:5432/fitness_db",
    ],
)
def test_database_url_is_forced_to_psycopg3(url: str) -> None:
    assert normalize_database_url(url) == "postgresql+psycopg://u:p@db:5432/fitness_db"
