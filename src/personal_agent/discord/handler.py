from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import discord

from personal_agent.agent.tool_loop import AgentResponse

THINKING_GIF_PATH = Path(__file__).resolve().parent.parent / "assets" / "clawd-thinking.gif"


class MessageAuthorizer:
    def __init__(self, guild_id: int, channel_id: int, owner_user_ids: int | list[int]) -> None:
        self.guild_id, self.channel_id = guild_id, channel_id
        self.owner_user_ids = {owner_user_ids} if isinstance(owner_user_ids, int) else set(owner_user_ids)

    def allows(self, message: Any) -> bool:
        return (
            not message.author.bot
            and message.guild is not None
            and message.guild.id == self.guild_id
            and message.channel.id == self.channel_id
            and message.author.id in self.owner_user_ids
        )


async def handle_message(
    message: Any, authorizer: MessageAuthorizer, respond: Callable[..., Awaitable[AgentResponse]]
) -> AgentResponse | None:
    if not authorizer.allows(message):
        return None
    content = message.content.strip()
    if content:
        status_message = None

        async def show_thinking() -> None:
            nonlocal status_message
            if status_message is None:
                if THINKING_GIF_PATH.is_file():
                    try:
                        status_message = await message.channel.send(
                            file=discord.File(THINKING_GIF_PATH, filename="clawd-thinking.gif")
                        )
                    except TypeError:
                        status_message = await message.channel.send("🤔 Thinking...")
                else:
                    status_message = await message.channel.send("🤔 Thinking...")

        try:
            async with message.channel.typing():
                response = await respond(content, on_tool_started=show_thinking)
            reply = response.content.strip() or "已完成。"
        except Exception:
            error_msg = "❌ Failed：處理訊息時發生錯誤，請查看服務日誌。"
            if status_message is None:
                status_message = await message.channel.send(error_msg)
            else:
                try:
                    await status_message.edit(content=error_msg, attachments=[])
                except TypeError:
                    await status_message.edit(content=error_msg)
            raise
        if response.used_tools and status_message is not None:
            final_content = f"❌ Failed\n\n{reply}" if response.tool_failed else reply
            try:
                await status_message.edit(content=final_content, attachments=[])
            except TypeError:
                await status_message.edit(content=final_content)
        else:
            await message.channel.send(reply)
        return response
    return None
