from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.query import SearchNotionArgs

from .client import NotionClient, NotionError


class NotionSearchService:
    def __init__(self, client: NotionClient, sources: dict[str, tuple[str, str]]) -> None:
        self.client = client
        self.sources = sources

    async def search(self, args: SearchNotionArgs) -> ToolResult:
        aliases = [args.database] if args.database else list(self.sources)
        results: list[dict[str, object]] = []
        try:
            for alias in aliases:
                if alias is None or alias not in self.sources:
                    continue
                data_source_id, title_property = self.sources[alias]
                pages = await self.client.query_data_source(
                    data_source_id,
                    {
                        "filter": {"property": title_property, "title": {"contains": args.query}},
                        "page_size": min(args.limit, 100),
                    },
                )
                for page in pages:
                    title_items = page.get("properties", {}).get(title_property, {}).get("title", [])
                    title = "".join(item.get("plain_text", "") for item in title_items)
                    results.append({"database": alias, "id": page.get("id", ""), "title": title, "url": page.get("url", "")})
                    if len(results) >= args.limit:
                        return ToolResult.ok({"results": results, "count": len(results)})
            return ToolResult.ok({"results": results, "count": len(results)})
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))
