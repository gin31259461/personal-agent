from typing import Any, cast

import httpx

from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.query import WebSearchArgs


class SearxngSearchService:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_results: int,
        max_response_bytes: int = 262144,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_results = max_results
        self.max_response_bytes = max_response_bytes
        self.client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def search(self, args: WebSearchArgs) -> ToolResult:
        params: dict[str, str | int] = {"q": args.query, "format": "json"}
        if args.freshness_days is not None:
            params["time_range"] = "day" if args.freshness_days <= 1 else "month"
        try:
            response = await self.client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()
            if len(response.content) > self.max_response_bytes:
                return ToolResult.fail("WEB_SEARCH_TOO_LARGE", "Web search response exceeded the configured limit")
            body = cast(dict[str, Any], response.json())
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult.fail("WEB_SEARCH_FAILED", f"Web search failed ({type(exc).__name__})")
        count = min(args.count, self.max_results)
        results = [
            {
                "title": str(item.get("title", ""))[:500],
                "url": str(item.get("url", ""))[:2000],
                "snippet": str(item.get("content", ""))[:1000],
                "published_at": item.get("publishedDate"),
            }
            for item in body.get("results", [])[:count]
            if isinstance(item, dict)
        ]
        return ToolResult.ok({"results": results, "count": len(results)})
