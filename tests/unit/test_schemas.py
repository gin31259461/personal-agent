from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from personal_agent.schemas.expense import AddExpenseArgs
from personal_agent.schemas.task import CreateTaskArgs


def test_task_schema_strips_title():
    args = CreateTaskArgs(title="  整理房間 ", description="  清理房間 ")
    assert args.title == "整理房間"
    assert args.description == "清理房間"


def test_expense_requires_positive_amount():
    with pytest.raises(ValidationError):
        AddExpenseArgs(title="午餐", amount=0, date=date.today())


def test_expense_accepts_decimal():
    args = AddExpenseArgs(title="午餐", amount="120", date=date.today())
    assert args.amount == Decimal("120")
