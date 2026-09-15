from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs, AddTransactionArgs
from personal_agent.schemas.query import QueryExpensesArgs

from .client import NotionClient, NotionError
from .mapping import date_property, merge, number_property, relation_property, select_property, title_property
from .relations import RelationResolver


class FinanceService:
    def __init__(
        self,
        client: NotionClient,
        data_source_id: str,
        properties: dict[str, str],
        resolver: RelationResolver | None = None,
        category_data_source_id: str | None = None,
        account_data_source_id: str | None = None,
    ) -> None:
        self.client, self.data_source_id, self.properties = client, data_source_id, properties
        self.resolver = resolver
        self.category_data_source_id = category_data_source_id
        self.account_data_source_id = account_data_source_id

    async def add(self, args: AddExpenseArgs, external_id: str | None = None) -> ToolResult:
        p = self.properties
        properties = merge(
            title_property(p["title"], args.title), number_property(p["amount"], args.amount), date_property(p["date"], args.date)
        )
        if p.get("type"):
            properties.update(select_property(p["type"], getattr(args, "type", "Expense")))
        try:
            if args.category and self.resolver and self.category_data_source_id and p.get("category"):
                category = await self.resolver.resolve(self.category_data_source_id, "Category Name", args.category)
                properties.update(relation_property(p["category"], [category.id]))
            if args.account and self.resolver and self.account_data_source_id and p.get("account"):
                account = await self.resolver.resolve(self.account_data_source_id, "Account Name", args.account)
                properties.update(relation_property(p["account"], [account.id]))
            page = await self.client.create_page(self.data_source_id, properties)
            return ToolResult.ok(
                {"expense_id": page.get("id", ""), "title": args.title, "amount": str(args.amount), "date": args.date.isoformat()}
            )
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))

    async def add_transaction(self, args: AddTransactionArgs) -> ToolResult:
        result = await self.add(args)
        return result

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
