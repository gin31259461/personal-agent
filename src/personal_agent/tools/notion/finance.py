from typing import TYPE_CHECKING

from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs, AddTransactionArgs
from personal_agent.schemas.query import QueryExpensesArgs

from .client import NotionClient, NotionError
from .mapping import date_property, merge, number_property, relation_property, select_property, title_property
from .relations import RelationResolver

if TYPE_CHECKING:
    from .schema import NotionSchemaCache


class FinanceService:
    def __init__(
        self,
        client: NotionClient,
        data_source_id: str,
        properties: dict[str, str] | None = None,
        resolver: RelationResolver | None = None,
        category_data_source_id: str | None = None,
        account_data_source_id: str | None = None,
        schema_cache: "NotionSchemaCache | None" = None,
    ) -> None:
        self.client, self.data_source_id = client, data_source_id
        self.properties = dict(properties or {})
        self.resolver = resolver
        self.category_data_source_id = category_data_source_id
        self.account_data_source_id = account_data_source_id
        self.schema_cache = schema_cache

    async def _get_properties(self) -> dict[str, str]:
        if self.schema_cache:
            return await self.schema_cache.resolve_finance_properties(self.data_source_id, self.properties)
        fallback = {"title": "Item Name", "amount": "Amount", "date": "Date"}
        fallback.update(self.properties)
        return fallback

    async def add(self, args: AddExpenseArgs, external_id: str | None = None) -> ToolResult:
        try:
            p = await self._get_properties()
            title_prop = p.get("title", "Item Name")
            amount_prop = p.get("amount", "Amount")
            date_prop = p.get("date", "Date")

            properties = merge(
                title_property(title_prop, args.title),
                number_property(amount_prop, args.amount),
                date_property(date_prop, args.date),
            )
            if p.get("type"):
                properties.update(select_property(p["type"], getattr(args, "type", "Expense")))

            if args.category and p.get("category"):
                cat_target_id = self.category_data_source_id
                if not cat_target_id and self.schema_cache:
                    cat_target_id = await self.schema_cache.get_relation_target_data_source_id(self.data_source_id, p["category"])
                if cat_target_id and self.resolver:
                    cat_title = (
                        await self.schema_cache.get_title_property_name(cat_target_id) if self.schema_cache else "Category Name"
                    )
                    category = await self.resolver.resolve(cat_target_id, cat_title, args.category)
                    properties.update(relation_property(p["category"], [category.id]))
                elif not cat_target_id:
                    properties.update(select_property(p["category"], args.category.name or args.category.id or ""))

            if args.account and p.get("account"):
                acc_target_id = self.account_data_source_id
                if not acc_target_id and self.schema_cache:
                    acc_target_id = await self.schema_cache.get_relation_target_data_source_id(self.data_source_id, p["account"])
                if acc_target_id and self.resolver:
                    acc_title = (
                        await self.schema_cache.get_title_property_name(acc_target_id) if self.schema_cache else "Account Name"
                    )
                    account = await self.resolver.resolve(acc_target_id, acc_title, args.account)
                    properties.update(relation_property(p["account"], [account.id]))
                elif not acc_target_id:
                    properties.update(select_property(p["account"], args.account.name or args.account.id or ""))

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
        try:
            p = await self._get_properties()
            date_prop = p.get("date", "Date")
            filters = []
            if args.start_date:
                filters.append({"property": date_prop, "date": {"on_or_after": args.start_date.isoformat()}})
            if args.end_date:
                filters.append({"property": date_prop, "date": {"on_or_before": args.end_date.isoformat()}})
            body = {"filter": {"and": filters}} if len(filters) > 1 else ({"filter": filters[0]} if filters else {})
            pages = await self.client.query_data_source(self.data_source_id, body)
            expenses = [{"id": page.get("id", ""), "url": page.get("url", "")} for page in pages]
            return ToolResult.ok({"expenses": expenses, "count": len(expenses)})
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))
