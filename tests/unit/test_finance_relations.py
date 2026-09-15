from datetime import date

import pytest

from personal_agent.schemas.expense import AddExpenseArgs
from personal_agent.tools.notion.finance import FinanceService
from personal_agent.tools.notion.relations import ResolvedRelation


class FakeNotion:
    properties = None

    async def create_page(self, data_source_id, properties, children=None):
        self.properties = properties
        return {"id": "transaction-id"}


class FakeResolver:
    async def resolve(self, data_source_id, title_property, reference):
        return ResolvedRelation(f"{title_property}-id", reference.name or "")


@pytest.mark.asyncio
async def test_expense_writes_category_and_account_relations():
    notion = FakeNotion()
    service = FinanceService(
        notion,
        "transactions",
        {"title": "Item Name", "amount": "Amount", "date": "Date", "type": "Type", "category": "Category", "account": "Account"},
        FakeResolver(),
        "categories",
        "accounts",
    )
    result = await service.add(
        AddExpenseArgs(title="早餐", amount="120", date=date(2026, 9, 15), category={"name": "餐飲"}, account={"name": "現金"})
    )
    assert result.success is True
    assert notion.properties["Category"] == {"relation": [{"id": "Category Name-id"}]}
    assert notion.properties["Account"] == {"relation": [{"id": "Account Name-id"}]}
