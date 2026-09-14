
import pytest

from personal_agent.agent.tool_loop import run_tool_loop
from personal_agent.llm.models import AssistantResponse, Message, ToolCall
from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.tools.base import RegisteredTool, ToolRisk
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.policy import Policy
from personal_agent.tools.registry import ToolRegistry


class FakeLLM:
    def __init__(self):
        self.messages = []
        self.calls = 0

    async def chat(self, messages, tools):
        self.messages.append([message.model_dump(exclude_none=True) for message in messages])
        self.calls += 1
        if self.calls == 1:
            return AssistantResponse(
                tool_calls=[ToolCall(id="call-1", name="task", arguments={"title": "買牛奶"})]
            )
        return AssistantResponse(content="已完成")


@pytest.mark.asyncio
async def test_tool_call_is_serialized_for_follow_up_llm_request():
    registry = ToolRegistry()

    async def create_task(_):
        return ToolResult.ok({"created": True})

    registry.register(RegisteredTool("task", "Create a task", CreateTaskArgs, create_task, ToolRisk.WRITE_SAFE))
    llm = FakeLLM()
    result = await run_tool_loop(
        [Message(role="user", content="建立任務")],
        llm,
        registry,
        ToolExecutor(registry, Policy()),
        max_iterations=2,
    )

    assert result == "已完成"
    assert llm.messages[1][1]["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "task", "arguments": '{"title": "買牛奶"}'},
        }
    ]
