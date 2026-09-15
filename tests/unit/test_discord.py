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
async def test_tool_task_changes_thinking_to_done():
    sent = []
    msg = message()

    async def send(value):
        status = SimpleNamespace(content=value)

        async def edit(*, content):
            status.content = content

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
    assert sent[0].content == "✅ Done\n\n建立完成"


@pytest.mark.asyncio
async def test_failed_tool_changes_thinking_to_failed():
    sent = []
    msg = message()

    async def send(value):
        status = SimpleNamespace(content=value)

        async def edit(*, content):
            status.content = content

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


async def _reply(*args, **kwargs):
    from personal_agent.agent.tool_loop import AgentResponse

    return AgentResponse("reply")


async def _empty_reply():
    return ""


async def _failed_reply(*args, **kwargs):
    raise RuntimeError("boom")
