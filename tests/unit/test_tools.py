from datetime import date

import pytest

from personal_agent.schemas.expense import AddExpenseArgs
from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.tools.base import RegisteredTool, ToolRisk
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.policy import Policy
from personal_agent.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected():
    executor = ToolExecutor(ToolRegistry(), Policy())
    result = await executor.execute("delete_notion_database", {})
    assert result.error_code == "UNKNOWN_TOOL"


@pytest.mark.asyncio
async def test_invalid_arguments_do_not_execute():
    called = False

    async def handler(_):
        nonlocal called
        called = True
        return None

    registry = ToolRegistry()
    registry.register(RegisteredTool("task", "", CreateTaskArgs, handler, ToolRisk.WRITE_SAFE))
    result = await ToolExecutor(registry, Policy()).execute("task", {"title": ""})
    assert result.error_code == "INVALID_ARGUMENTS"
    assert not called


@pytest.mark.asyncio
async def test_sensitive_tools_require_confirmation():
    async def handler(_):
        from personal_agent.schemas.common import ToolResult

        return ToolResult.ok()

    registry = ToolRegistry()
    registry.register(RegisteredTool("expense", "", AddExpenseArgs, handler, ToolRisk.WRITE_SENSITIVE))
    args = {"title": "午餐", "amount": 120, "date": date.today().isoformat()}
    result = await ToolExecutor(registry, Policy()).execute("expense", args)
    assert result.error_code == "CONFIRMATION_REQUIRED"
