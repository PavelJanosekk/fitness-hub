import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime, one_of
from app.timeutils import now_utc


class Assistant(StrEnum):
    coach = "coach"
    nutrition = "nutrition"  # Phase 5


class ChatRole(StrEnum):
    user = "user"
    model = "model"


class ChatConversation(SQLModel, table=True):
    __tablename__ = "chat_conversations"
    __table_args__ = (one_of("assistant", Assistant),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    assistant: str
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
    updated_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"
    __table_args__ = (one_of("role", ChatRole),)

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="chat_conversations.id", ondelete="CASCADE", index=True)
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = Field(default=None, sa_type=JSONB)
    created_at: dt.datetime = Field(default_factory=now_utc, sa_type=AwareDateTime)
