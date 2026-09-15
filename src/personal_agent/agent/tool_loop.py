import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from personal_agent.llm.models import Message
from personal_agent.llm.protocol import ChatClient
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.registry import ToolRegistry


class MaxToolIterationsExceeded(Exception):
    pass


@dataclass(frozen=True)
class AgentResponse:
    content: str
    used_tools: bool = False
    tool_failed: bool = False
    clarification_required: bool = False


ToolStartedHandler = Callable[[], Awaitable[None]]


async def run_tool_loop(
    messages: list[Message],
    llm: ChatClient,
    registry: ToolRegistry,
    executor: ToolExecutor,
    max_iterations: int,
    on_tool_started: ToolStartedHandler | None = None,
) -> AgentResponse:
    used_tools = False
    tool_failed = False
    clarification_required = False
    for _ in range(max_iterations):
        response = await llm.chat(messages, registry.definitions())
        if not response.tool_calls:
            return AgentResponse(response.content or "", used_tools, tool_failed, clarification_required)
        if not used_tools and on_tool_started:
            await on_tool_started()
        used_tools = True
        messages.append(
            Message(
                role="assistant",
                content=response.content,
                tool_calls=[
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in response.tool_calls
                ],
            )
        )
        for call in response.tool_calls:
            result = await executor.execute(call.name, call.arguments)
            if result.error_code in {"RELATION_NOT_FOUND", "RELATION_AMBIGUOUS", "INVALID_ARGUMENTS"}:
                clarification_required = True
            else:
                tool_failed = tool_failed or not result.success
            messages.append(Message(role="tool", tool_call_id=call.id, content=result.model_dump_json()))
    raise MaxToolIterationsExceeded
