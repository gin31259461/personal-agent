from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from personal_agent.agent.prompt import system_prompt
from personal_agent.llm.models import Message
from personal_agent.llm.protocol import ChatClient
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.registry import ToolRegistry

from .tool_loop import AgentResponse, ToolStartedHandler, run_tool_loop


class AgentRuntime:
    def __init__(
        self,
        llm: ChatClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        timezone: str = "Asia/Taipei",
        max_iterations: int = 5,
        preferences: str = "",
        closers: Sequence[Callable[[], Awaitable[None]]] | None = None,
        clarification_ttl_seconds: int = 600,
    ) -> None:
        self.llm, self.registry, self.executor = llm, registry, executor
        self.timezone, self.max_iterations = timezone, max_iterations
        self.preferences = preferences
        self.closers = closers or []
        self.clarification_ttl_seconds = clarification_ttl_seconds

    async def close(self) -> None:
        for closer in reversed(self.closers):
            await closer()

    async def respond(
        self,
        user_message: str,
        history: list[Message] | None = None,
        on_tool_started: ToolStartedHandler | None = None,
    ) -> AgentResponse:
        now = datetime.now(ZoneInfo(self.timezone))
        messages = [Message(role="system", content=system_prompt(now, self.timezone, self.preferences))]
        messages.extend((history or [])[-20:])
        messages.append(Message(role="user", content=user_message))
        return await run_tool_loop(messages, self.llm, self.registry, self.executor, self.max_iterations, on_tool_started)
