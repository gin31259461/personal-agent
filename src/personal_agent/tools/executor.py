from typing import Any

from pydantic import ValidationError

from personal_agent.schemas.common import ToolResult

from .policy import Policy
from .registry import ToolNotFound, ToolRegistry


class ToolExecutionError(Exception):
    pass


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: Policy) -> None:
        self.registry, self.policy = registry, policy

    async def execute(self, name: str, arguments: dict[str, Any], confirmed: bool = False) -> ToolResult:
        try:
            tool = self.registry.get(name)
            args = tool.validate(arguments)
        except ToolNotFound:
            return ToolResult.fail("UNKNOWN_TOOL", f"Unknown tool: {name}")
        except ValidationError as exc:
            return ToolResult.fail("INVALID_ARGUMENTS", str(exc))
        decision = self.policy.evaluate(tool)
        if not decision.allowed:
            return ToolResult.fail("POLICY_DENIED", decision.reason or "operation denied")
        if decision.requires_confirmation and not confirmed:
            return ToolResult.fail("CONFIRMATION_REQUIRED", "This operation requires confirmation")
        try:
            return await tool.handler(args)
        except Exception as exc:
            return ToolResult.fail("TOOL_ERROR", str(exc))
