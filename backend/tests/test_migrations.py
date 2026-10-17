from sqlalchemy import text
from sqlmodel import Session


def test_search_extensions_are_installed(session: Session) -> None:
    installed = set(session.connection().execute(text("SELECT extname FROM pg_extension")).scalars())

    assert {"pg_trgm", "unaccent"} <= installed


def test_f_unaccent_strips_czech_diacritics(session: Session) -> None:
    result = session.connection().execute(text("SELECT f_unaccent('Kuřecí stehno, žervé')")).scalar_one()

    assert result == "Kureci stehno, zerve"
