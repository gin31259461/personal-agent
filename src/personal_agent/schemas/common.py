from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolResult(StrictModel):
    success: bool
    data: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def ok(cls, data: dict[str, object] | None = None) -> "ToolResult":
        return cls(success=True, data=data or {})

    @classmethod
    def fail(cls, code: str, message: str) -> "ToolResult":
        return cls(success=False, error_code=code, error_message=message)
