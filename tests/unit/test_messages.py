from datetime import UTC, datetime, timedelta

import pytest

from personal_agent.llm.models import Message
from personal_agent.storage.db import Database
from personal_agent.storage.repositories.messages import MessageRepository


@pytest.fixture
async def db():
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_message_repository_add_and_retrieve_recent(db: Database):
    async with db.session() as session:
        repo = MessageRepository(session, ttl_seconds=3600)
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi, how can I help?"),
            Message(role="user", content="What is the weather?"),
            Message(role="assistant", content="It is sunny."),
        ]
        await repo.add_messages("chan-1", messages)

        recent = await repo.get_recent_messages("chan-1", limit=10)
        assert len(recent) == 4
        assert [m.content for m in recent] == [
            "Hello",
            "Hi, how can I help?",
            "What is the weather?",
            "It is sunny.",
        ]
        assert [m.role for m in recent] == ["user", "assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_message_repository_limit(db: Database):
    async with db.session() as session:
        repo = MessageRepository(session, ttl_seconds=3600)
        messages = [Message(role="user", content=f"msg-{i}") for i in range(10)]
        await repo.add_messages("chan-1", messages)

        recent = await repo.get_recent_messages("chan-1", limit=3)
        assert len(recent) == 3
        # Should be the 3 most recent in chronological order
        assert [m.content for m in recent] == ["msg-7", "msg-8", "msg-9"]


@pytest.mark.asyncio
async def test_message_repository_ttl_expiration(db: Database):
    async with db.session() as session:
        repo = MessageRepository(session, ttl_seconds=60)
        await repo.add_messages("chan-1", [Message(role="user", content="old message")])

        conv = await repo.get_active_conversation("chan-1")
        # Manually backdate the updated_at to simulate expiration
        conv.updated_at = datetime.now(UTC) - timedelta(seconds=120)
        await session.commit()

        # Should now return empty because the active conversation expired
        recent = await repo.get_recent_messages("chan-1")
        assert recent == []

        # A new conversation should be created upon next interaction
        await repo.add_messages("chan-1", [Message(role="user", content="new message")])
        new_recent = await repo.get_recent_messages("chan-1")
        assert len(new_recent) == 1
        assert new_recent[0].content == "new message"
