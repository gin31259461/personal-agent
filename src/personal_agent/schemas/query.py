from datetime import date

from pydantic import Field

from .common import StrictModel


class ListTasksArgs(StrictModel):
    status: str | None = Field(default=None, max_length=100)


class QueryExpensesArgs(StrictModel):
    start_date: date | None = None
    end_date: date | None = None
