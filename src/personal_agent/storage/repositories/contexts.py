import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PendingContext


class PendingContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, guild_id: str, channel_id: str, user_id: str) -> PendingContext | None:
        await self.session.execute(delete(PendingContext).where(PendingContext.expires_at <= datetime.now(UTC)))
        query = select(PendingContext).where(
            PendingContext.discord_guild_id == guild_id,
            PendingContext.discord_channel_id == channel_id,
            PendingContext.discord_user_id == user_id,
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def clear(self, guild_id: str, channel_id: str, user_id: str) -> None:
        await self.session.execute(
            delete(PendingContext).where(
                PendingContext.discord_guild_id == guild_id,
                PendingContext.discord_channel_id == channel_id,
                PendingContext.discord_user_id == user_id,
            )
        )
        await self.session.commit()

    async def save_dialogue(
        self, guild_id: str, channel_id: str, user_id: str, user_message: str, assistant_message: str, ttl_seconds: int
    ) -> None:
        await self.clear(guild_id, channel_id, user_id)
        now = datetime.now(UTC)
        self.session.add(
            PendingContext(
                id=str(uuid4()),
                discord_guild_id=guild_id,
                discord_channel_id=channel_id,
                discord_user_id=user_id,
                tool_name="clarification",
                arguments_json=json.dumps({"user": user_message, "assistant": assistant_message}),
                missing_field="",
                candidates_json="[]",
                expires_at=now + timedelta(seconds=ttl_seconds),
                created_at=now,
            )
        )
        await self.session.commit()
