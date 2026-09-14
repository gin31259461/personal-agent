from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs
from personal_agent.schemas.query import QueryExpensesArgs

from .client import NotionClient, NotionError
from .mapping import date_property, merge, number_property, rich_text_property, select_property, title_property


class FinanceService:
    def __init__(self, client: NotionClient, data_source_id: str, properties: dict[str, str]) -> None:
        self.client, self.data_source_id, self.properties = client, data_source_id, properties

    async def add(self, args: AddExpenseArgs, external_id: str | None = None) -> ToolResult:
        p = self.properties
        properties = merge(
            title_property(p["title"], args.title), number_property(p["amount"], args.amount), date_property(p["date"], args.date)
        )
        if p.get("type"):
            properties.update(select_property(p["type"], "Expense"))
        if args.category and p.get("category"):
            properties.update(select_property(p["category"], args.category))
        if args.payment_method and p.get("payment_method"):
            properties.update(select_property(p["payment_method"], args.payment_method))
        if args.note and p.get("note"):
            properties.update(rich_text_property(p["note"], args.note))
        if external_id and p.get("external_id"):
            properties.update(rich_text_property(p["external_id"], external_id))
        try:
            page = await self.client.create_page(self.data_source_id, properties)
            return ToolResult.ok(
                {"expense_id": page.get("id", ""), "title": args.title, "amount": str(args.amount), "date": args.date.isoformat()}
            )
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))

    async def query(self, args: QueryExpensesArgs) -> ToolResult:
        filters = []
        if args.start_date:
            filters.append({"property": self.properties["date"], "date": {"on_or_after": args.start_date.isoformat()}})
        if args.end_date:
            filters.append({"property": self.properties["date"], "date": {"on_or_before": args.end_date.isoformat()}})
        body = {"filter": {"and": filters}} if len(filters) > 1 else ({"filter": filters[0]} if filters else {})
        try:
            pages = await self.client.query_data_source(self.data_source_id, body)
            expenses = [{"id": page.get("id", ""), "url": page.get("url", "")} for page in pages]
            return ToolResult.ok({"expenses": expenses, "count": len(expenses)})
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))
