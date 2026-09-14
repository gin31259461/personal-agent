import json

from personal_agent.llm.models import Message
from personal_agent.llm.protocol import ChatClient
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.registry import ToolRegistry


class MaxToolIterationsExceeded(Exception):
    pass


async def run_tool_loop(
    messages: list[Message], llm: ChatClient, registry: ToolRegistry, executor: ToolExecutor, max_iterations: int
) -> str:
    for _ in range(max_iterations):
        response = await llm.chat(messages, registry.definitions())
        if not response.tool_calls:
            return response.content or ""
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
            messages.append(Message(role="tool", tool_call_id=call.id, content=result.model_dump_json()))
    raise MaxToolIterationsExceeded
