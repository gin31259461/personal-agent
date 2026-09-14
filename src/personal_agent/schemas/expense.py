from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator

from .common import StrictModel


class AddExpenseArgs(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    date: date
    category: str | None = Field(default=None, max_length=200)
    payment_method: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("title")
    @classmethod
    def title_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value
