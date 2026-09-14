from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .common import StrictModel


class CreateTaskArgs(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"] | None = None
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional short summary shown in the Notion Description property. Omit it when the title is sufficient.",
    )
    body: str | None = Field(
        default=None,
        max_length=20000,
        description="Full task details in Markdown. This becomes the Notion page body.",
    )

    @field_validator("title")
    @classmethod
    def title_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("description")
    @classmethod
    def description_must_have_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("description must not be empty")
        return value
