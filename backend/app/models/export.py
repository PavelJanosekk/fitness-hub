import datetime as dt

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime


class RepoExportState(SQLModel, table=True):
    """Single row (id = 1): the last data export into the private analysis repo (E40)."""

    __tablename__ = "repo_export_state"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: int = Field(default=1, primary_key=True)
    last_run_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)  # last attempt, changed or not
    last_success_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    last_commit_sha: str | None = None  # the newest export commit; unchanged runs make no commit
    last_changed_files: int = 0
    last_error: str | None = None
    # A public repo the user confirmed sharing health data into; the export refuses any other public repo
    public_ok_repo: str | None = None
