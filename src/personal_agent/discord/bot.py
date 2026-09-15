import json
from typing import Any, cast

from discord.ext import commands

from personal_agent.agent.tool_loop import AgentResponse
from personal_agent.llm.models import Message
from personal_agent.storage.db import Database
from personal_agent.storage.repositories.contexts import PendingContextRepository
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
            f"Discord message event guild={guild_id} channel={channel_id} author={author_id} bot={is_bot} allowed={allowed}",
            flush=True,
        )
        async with self.database.session() as session:
            events = ProcessedEventRepository(session)
            if not await events.claim(str(message.id)):
                print("Discord message skipped: event already claimed", flush=True)
                return
            print("Discord message claimed; starting response", flush=True)
            try:
                contexts = PendingContextRepository(session)
                guild_key, channel_key, user_key = str(guild_id), str(channel_id), str(author_id)
                pending = await contexts.get(guild_key, channel_key, user_key)
                history = None
                if pending:
                    dialogue = json.loads(pending.arguments_json)
                    history = [
                        Message(role="user", content=dialogue["user"]),
                        Message(role="assistant", content=dialogue["assistant"]),
                    ]

                async def respond(content: str, **kwargs: Any) -> AgentResponse:
                    return cast(AgentResponse, await self.runtime.respond(content, history=history, **kwargs))

                response = await handle_message(message, self.authorizer, respond)
                if response and response.clarification_required:
                    await contexts.save_dialogue(
                        guild_key,
                        channel_key,
                        user_key,
                        message.content.strip(),
                        response.content,
                        self.runtime.clarification_ttl_seconds,
                    )
                elif pending:
                    await contexts.clear(guild_key, channel_key, user_key)
            except Exception as exc:
                print(f"Discord response failed: {type(exc).__name__}: {exc}", flush=True)
                raise
            await events.complete(str(message.id))
            print("Discord response completed", flush=True)

    async def on_ready(self) -> None:
        if self.user:
            print(f"Logged in as {self.user}", flush=True)
