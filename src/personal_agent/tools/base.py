from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from personal_agent.llm.models import ToolDefinition
from personal_agent.schemas.common import ToolResult


class ToolRisk(StrEnum):
    READ = "read"
    WRITE_SAFE = "write_safe"
    WRITE_SENSITIVE = "write_sensitive"
    DESTRUCTIVE = "destructive"


ToolHandler = Callable[[Any], Awaitable[ToolResult]]


class RegisteredTool:
    def __init__(self, name: str, description: str, schema: type[BaseModel], handler: ToolHandler, risk: ToolRisk) -> None:
        self.name, self.description, self.schema = name, description, schema
        self.handler, self.risk = handler, risk

    def definition(self) -> ToolDefinition:
        schema = self.schema.model_json_schema()
        return ToolDefinition(name=self.name, description=self.description, parameters=schema)

    def validate(self, arguments: dict[str, Any]) -> BaseModel:
        return self.schema.model_validate(arguments)
