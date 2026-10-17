"""Chat conversations shared by the assistants (coach, nutrition): each keeps its own (decision E2)."""

import uuid

from google.genai import types
from sqlmodel import Session, col, select

from app.models.chat import Assistant, ChatConversation, ChatMessage, ChatRole
from app.services.gemini_service import AssistantReply, history_content
from app.timeutils import now_utc

HISTORY_MESSAGES = 30


def get_conversation(session: Session, conversation_id: uuid.UUID | None, assistant: Assistant) -> ChatConversation:
    """Existing conversation of this assistant, or a new one (with the client's id when given)."""
    if conversation_id is not None and (existing := session.get(ChatConversation, conversation_id)) is not None:
        if existing.assistant != assistant:
            raise ValueError("Conversation belongs to another assistant")
        return existing
    conversation = ChatConversation(id=conversation_id or uuid.uuid4(), assistant=assistant)
    session.add(conversation)
    session.flush()
    return conversation


def load_history(session: Session, conversation: ChatConversation) -> list[types.Content]:
    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(col(ChatMessage.id).desc())
        .limit(HISTORY_MESSAGES)
    ).all()
    return [history_content(m.role, m.content) for m in reversed(messages)]


def store_turn(session: Session, conversation: ChatConversation, user_text: str, result: AssistantReply) -> None:
    session.add(ChatMessage(conversation_id=conversation.id, role=ChatRole.user, content=user_text))
    session.add(
        ChatMessage(
            conversation_id=conversation.id, role=ChatRole.model, content=result.reply, tool_calls=result.tool_calls
        )
    )
    conversation.updated_at = now_utc()
    session.add(conversation)
    session.commit()
