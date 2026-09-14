from types import SimpleNamespace

import pytest

from personal_agent.discord.handler import MessageAuthorizer, handle_message


def message(user=1, channel=2, guild=3, bot=False, content="hello"):
    return SimpleNamespace(
        author=SimpleNamespace(id=user, bot=bot),
        channel=SimpleNamespace(id=channel),
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
    await handle_message(msg, MessageAuthorizer(3, 2, 1), lambda _: _empty_reply())
    assert sent[0].content == "✅ Done\n\n已完成。"


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
    await handle_message(msg, MessageAuthorizer(3, 2, 1), _reply)
    assert sent[0].content == "✅ Done\n\nreply"


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


async def _reply(_=None):
    return "reply"


async def _empty_reply():
    return ""


async def _failed_reply(_):
    raise RuntimeError("boom")
