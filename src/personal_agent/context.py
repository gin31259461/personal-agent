from contextvars import ContextVar

current_discord_user_id: ContextVar[str | None] = ContextVar("current_discord_user_id", default=None)
