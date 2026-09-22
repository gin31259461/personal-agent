from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from personal_agent.discord.handler import MessageAuthorizer, handle_message


def message(user=1, channel=2, guild=3, bot=False, content="hello"):
    @asynccontextmanager
    async def typing():
        yield

    return SimpleNamespace(
        author=SimpleNamespace(id=user, bot=bot),
        channel=SimpleNamespace(id=channel, typing=typing),
        guild=SimpleNamespace(id=guild),
        content=content,
    )


@pytest.mark.asyncio
async def test_authorizer_only_allows_configured_identity():
    authorizer = MessageAuthorizer(3, 2, [1, 4])
    assert authorizer.allows(message())
    assert authorizer.allows(message(user=4))
    assert not authorizer.allows(message(user=9))
    assert not authorizer.allows(message(channel=9))
    assert not authorizer.allows(message(bot=True))


@pytest.mark.asyncio
async def test_unauthorized_message_is_ignored():
    sent = []
    msg = message(user=9)
    msg.channel.send = sent.append
    await handle_message(msg, MessageAuthorizer(3, 2, 1), lambda _: _reply())
    assert sent == []


@pytest.mark.asyncio
async def test_empty_response_still_confirms_completion():
    sent = []
    msg = message()

    async def send(value):
        status = SimpleNamespace(content=value)

        async def edit(*, content):
            status.content = content

        status.edit = edit
        sent.append(status)
        return status

    msg.channel.send = send

    async def respond(*args, **kwargs):
        from personal_agent.agent.tool_loop import AgentResponse

        return AgentResponse("")

    await handle_message(msg, MessageAuthorizer(3, 2, 1), respond)
    assert sent[0].content == "已完成。"


@pytest.mark.asyncio
async def test_pending_message_is_updated_with_reply():
    sent = []
    msg = message()

    async def send(value):
        status = SimpleNamespace(content=value)

        async def edit(*, content):
            status.content = content

        status.edit = edit
        sent.append(status)
        return status

    msg.channel.send = send

    async def respond(*args, **kwargs):
        from personal_agent.agent.tool_loop import AgentResponse

        return AgentResponse("reply")

    await handle_message(msg, MessageAuthorizer(3, 2, 1), respond)
    assert sent[0].content == "reply"


@pytest.mark.asyncio
async def test_tool_task_updates_thinking_message():
    sent = []
    msg = message()

    async def send(value=None, *, file=None, **kwargs):
        status = SimpleNamespace(content=value, file=file, attachments=[file] if file else [])

        async def edit(*, content=None, attachments=None, **kwargs):
            if content is not None:
                status.content = content
            if attachments is not None:
                status.attachments = attachments

        status.edit = edit
        sent.append(status)
        return status

    async def respond(*args, on_tool_started, **kwargs):
        from personal_agent.agent.tool_loop import AgentResponse

        await on_tool_started()
        return AgentResponse("建立完成", used_tools=True)

    msg.channel.send = send
    await handle_message(msg, MessageAuthorizer(3, 2, 1), respond)
    assert len(sent) == 1
    assert sent[0].content == "建立完成"
    assert sent[0].attachments == []
    assert sent[0].file is not None
    assert sent[0].file.filename == "clawd-thinking.gif"


@pytest.mark.asyncio
async def test_failed_tool_changes_thinking_to_failed():
    sent = []
    msg = message()

    async def send(value=None, *, file=None, **kwargs):
        status = SimpleNamespace(content=value, file=file, attachments=[file] if file else [])

        async def edit(*, content=None, attachments=None, **kwargs):
            if content is not None:
                status.content = content
            if attachments is not None:
                status.attachments = attachments

        status.edit = edit
        sent.append(status)
        return status

    async def respond(*args, on_tool_started, **kwargs):
        from personal_agent.agent.tool_loop import AgentResponse

        await on_tool_started()
        return AgentResponse("Notion 拒絕請求", used_tools=True, tool_failed=True)

    msg.channel.send = send
    await handle_message(msg, MessageAuthorizer(3, 2, 1), respond)
    assert sent[0].content == "❌ Failed\n\nNotion 拒絕請求"
    assert sent[0].attachments == []
    assert sent[0].file is not None


@pytest.mark.asyncio
async def test_failed_response_updates_pending_message():
    sent = []
    msg = message()

    async def send(value):
        status = SimpleNamespace(content=value)

        async def edit(*, content):
            status.content = content

        status.edit = edit
        sent.append(status)
        return status

    msg.channel.send = send
    with pytest.raises(RuntimeError, match="boom"):
        await handle_message(msg, MessageAuthorizer(3, 2, 1), _failed_reply)
    assert sent[0].content.startswith("❌ Failed")


@pytest.mark.asyncio
async def test_bot_on_message_preserves_and_injects_conversation_history():
    from personal_agent.agent.tool_loop import AgentResponse
    from personal_agent.discord.bot import PersonalAgentBot
    from personal_agent.storage.db import Database

    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()

    received_histories = []

    class MockRuntime:
        clarification_ttl_seconds = 600

        async def respond(self, content: str, history=None, **kwargs):
            received_histories.append(history)
            return AgentResponse(f"Echo: {content}")

    authorizer = MessageAuthorizer(guild_id=3, channel_id=2, owner_user_ids=1)
    bot = PersonalAgentBot(token="fake", authorizer=authorizer, runtime=MockRuntime(), database=database)

    async def send_msg(content):
        return SimpleNamespace(content=content, edit=lambda **kw: None)

    msg1 = message(user=1, channel=2, guild=3, content="Turn 1")
    msg1.id = 101
    msg1.channel.send = send_msg
    await bot.on_message(msg1)

    assert len(received_histories) == 1
    assert received_histories[0] == []  # First turn has no history

    msg2 = message(user=1, channel=2, guild=3, content="Turn 2")
    msg2.id = 102
    msg2.channel.send = send_msg
    await bot.on_message(msg2)

    assert len(received_histories) == 2
    assert len(received_histories[1]) == 2
    assert received_histories[1][0].role == "user"
    assert received_histories[1][0].content == "Turn 1"
    assert received_histories[1][1].role == "assistant"
    assert received_histories[1][1].content == "Echo: Turn 1"

    await database.close()


async def _reply(*args, **kwargs):
    from personal_agent.agent.tool_loop import AgentResponse

    return AgentResponse("reply")


async def _empty_reply():
    return ""


async def _failed_reply(*args, **kwargs):
    raise RuntimeError("boom")
