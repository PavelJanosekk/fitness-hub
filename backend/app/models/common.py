from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime

# Every timestamp column is timestamptz (docs/SPEC.md §3, "Time")
AwareDateTime = DateTime(timezone=True)


def one_of(column: str, values: type[StrEnum]) -> CheckConstraint:
    """CHECK constraint restricting a VARCHAR column to an enum's values.

    Plain strings + CHECK instead of native Postgres enums, which are painful to migrate.
    """
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return CheckConstraint(f"{column} IS NULL OR {column} IN ({allowed})", name=column)
