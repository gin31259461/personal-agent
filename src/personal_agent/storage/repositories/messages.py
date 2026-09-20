from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from personal_agent.llm.models import Message
from personal_agent.storage.models import Conversation, StoredMessage


class MessageRepository:
    def __init__(self, session: AsyncSession, ttl_seconds: int = 7200) -> None:
        self.session = session
        self.ttl_seconds = ttl_seconds

    async def get_active_conversation(self, channel_id: str) -> Conversation:
        now = datetime.now(UTC)
        query = (
            select(Conversation)
            .where(Conversation.discord_channel_id == channel_id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = (await self.session.execute(query)).scalar_one_or_none()

        if conversation is not None:
            updated_at = conversation.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            time_since_last_active = (now - updated_at).total_seconds()
            if time_since_last_active <= self.ttl_seconds:
                return conversation

        # No conversation or existing conversation expired: create a new one
        new_conv = Conversation(
            id=str(uuid4()),
            discord_channel_id=channel_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(new_conv)
        await self.session.commit()
        await self.session.refresh(new_conv)
        return new_conv

    async def get_recent_messages(self, channel_id: str, limit: int = 20) -> list[Message]:
        now = datetime.now(UTC)
        query = (
            select(Conversation)
            .where(Conversation.discord_channel_id == channel_id)
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        conversation = (await self.session.execute(query)).scalar_one_or_none()
        if conversation is None:
            return []

        updated_at = conversation.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        time_since_last_active = (now - updated_at).total_seconds()
        if time_since_last_active > self.ttl_seconds:
            return []

        msg_query = (
            select(StoredMessage)
            .where(StoredMessage.conversation_id == conversation.id)
            .order_by(StoredMessage.created_at.desc())
            .limit(limit)
        )
        stored_messages = (await self.session.execute(msg_query)).scalars().all()

        return [
            Message(role=sm.role, content=sm.content or "")
            for sm in reversed(stored_messages)
        ]

    async def add_messages(self, channel_id: str, messages: list[Message]) -> None:
        if not messages:
            return

        conversation = await self.get_active_conversation(channel_id)
        now = datetime.now(UTC)

        for idx, msg in enumerate(messages):
            stored_message = StoredMessage(
                id=str(uuid4()),
                conversation_id=conversation.id,
                role=msg.role,
                content=msg.content,
                created_at=now + timedelta(microseconds=idx),
            )
            self.session.add(stored_message)

        conversation.updated_at = now
        await self.session.commit()
