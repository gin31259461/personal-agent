from collections.abc import Awaitable, Callable
from typing import Any


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


async def handle_message(message: Any, authorizer: MessageAuthorizer, respond: Callable[[str], Awaitable[str]]) -> None:
    if not authorizer.allows(message):
        return
    content = message.content.strip()
    if content:
        status_message = await message.channel.send("⏳ Pending...")
        try:
            reply = (await respond(content)).strip() or "已完成。"
        except Exception:
            await status_message.edit(content="❌ Failed：處理訊息時發生錯誤，請查看服務日誌。")
            raise
        await status_message.edit(content=f"✅ Done\n\n{reply}")
