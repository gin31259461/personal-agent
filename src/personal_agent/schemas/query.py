from datetime import date

from pydantic import Field

from .common import StrictModel


class ListTasksArgs(StrictModel):
    status: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)
    start_cursor: str | None = None


class QueryExpensesArgs(StrictModel):
    start_date: date | None = None
    end_date: date | None = None
    type: str | None = Field(default=None, pattern="^(Income|Expense)$")
    limit: int = Field(default=20, ge=1, le=100)
    start_cursor: str | None = None


class SearchNotionArgs(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    database: str | None = Field(default=None, pattern="^(tasks|projects|transactions|categories|accounts)$")
    limit: int = Field(default=10, ge=1, le=25)


class WebSearchArgs(StrictModel):
    query: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=10)
    freshness_days: int | None = Field(default=None, ge=1, le=3650)
