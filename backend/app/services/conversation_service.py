"""
conversation_service.py — Business logic for conversation and message operations.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.core.constants import DEFAULT_CONVERSATION_TITLE
from app.schemas.conversation import ConversationResponse, ConversationListItem, MessageResponse


class ConversationService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)

    async def get_or_create_conversation(
        self, user_id: str, conversation_id: str | None, first_message: str | None = None
    ) -> dict:
        """
        If conversation_id is provided, load and return it.
        Otherwise create a new conversation with an auto-generated title.
        """
        if conversation_id:
            conv = await self._conv_repo.get_by_id(conversation_id)
            if not conv:
                raise ValueError(f"Conversation '{conversation_id}' not found.")
            return conv

        # Auto-generate title from first message (truncate at 60 chars)
        title = DEFAULT_CONVERSATION_TITLE
        if first_message:
            title = first_message[:60].strip()
            if len(first_message) > 60:
                title += "…"

        return await self._conv_repo.create(user_id=user_id, title=title)

    async def list_conversations(
        self, user_id: str, limit: int = 50, skip: int = 0
    ) -> list[ConversationListItem]:
        docs = await self._conv_repo.list_by_user(user_id, limit=limit, skip=skip)
        return [ConversationListItem(**d) for d in docs]

    async def get_conversation(self, conversation_id: str) -> ConversationResponse | None:
        doc = await self._conv_repo.get_by_id(conversation_id)
        if not doc:
            return None
        return ConversationResponse(**doc)

    async def list_messages(
        self, conversation_id: str, limit: int = 100, skip: int = 0
    ) -> list[MessageResponse]:
        docs = await self._msg_repo.list_by_conversation(conversation_id, limit=limit, skip=skip)
        return [MessageResponse(**d) for d in docs]
