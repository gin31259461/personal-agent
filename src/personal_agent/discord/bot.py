from typing import Any

from discord.ext import commands

from personal_agent.storage.db import Database
from personal_agent.storage.repositories.events import ProcessedEventRepository

from .handler import MessageAuthorizer, handle_message


class PersonalAgentBot(commands.Bot):
    def __init__(self, token: str, authorizer: MessageAuthorizer, runtime: Any, database: Database) -> None:
        intents = __import__("discord").Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.token, self.authorizer, self.runtime, self.database = token, authorizer, runtime, database

    async def on_message(self, message: Any) -> None:
        allowed = self.authorizer.allows(message)
        guild_id = getattr(message.guild, "id", None)
        channel_id = getattr(message.channel, "id", None)
        author_id = getattr(message.author, "id", None)
        is_bot = getattr(message.author, "bot", None)
        print(
            f"Discord message event guild={guild_id} channel={channel_id} "
            f"author={author_id} bot={is_bot} allowed={allowed}",
            flush=True,
        )
        async with self.database.session() as session:
            events = ProcessedEventRepository(session)
            if not await events.claim(str(message.id)):
                print("Discord message skipped: event already claimed", flush=True)
                return
            print("Discord message claimed; starting response", flush=True)
            try:
                await handle_message(message, self.authorizer, self.runtime.respond)
            except Exception as exc:
                print(f"Discord response failed: {type(exc).__name__}: {exc}", flush=True)
                raise
            await events.complete(str(message.id))
            print("Discord response completed", flush=True)

    async def on_ready(self) -> None:
        if self.user:
            print(f"Logged in as {self.user}", flush=True)
