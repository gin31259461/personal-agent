from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ProcessedEvent


class ProcessedEventRepository:
    """Claims Discord event ids atomically so gateway retries cannot repeat a tool call."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, event_id: str) -> bool:
        self.session.add(ProcessedEvent(id=event_id, status="processing", created_at=datetime.now(UTC)))
        try:
            await self.session.commit()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False

    async def complete(self, event_id: str) -> None:
        event = await self.session.get(ProcessedEvent, event_id)
        if event:
            event.status = "completed"
            await self.session.commit()
