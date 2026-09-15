from dataclasses import dataclass
from typing import Any, cast

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class NotionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _RetryableNotionResponse(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@dataclass(frozen=True)
class NotionPage:
    results: list[dict[str, Any]]
    has_more: bool
    next_cursor: str | None


class NotionClient:
    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, _RetryableNotionResponse)),
        wait=wait_exponential(multiplier=1, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def create_page(
        self,
        data_source_id: str,
        properties: dict[str, object],
        children: list[dict[str, object]] | None = None,
    ) -> dict[str, Any]:
        try:
            payload: dict[str, object] = {
                "parent": {"data_source_id": data_source_id},
                "properties": properties,
            }
            if children:
                payload["children"] = children
            response = await self._client.post("/pages", json=payload)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise _RetryableNotionResponse(response.status_code)
            if response.status_code >= 400:
                raise NotionError(f"NOTION_{response.status_code}", "Notion rejected the request")
            return cast(dict[str, Any], response.json())
        except httpx.TimeoutException as exc:
            raise NotionError("NOTION_TIMEOUT", "Notion API request timed out") from exc
        except _RetryableNotionResponse as exc:
            raise NotionError(f"NOTION_{exc.status_code}", "Notion API temporarily unavailable") from exc
        except httpx.TransportError as exc:
            raise NotionError("NOTION_NETWORK", "Notion API network error") from exc

    async def query_data_source(self, data_source_id: str, filter_body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            response = await self._client.post(f"/data_sources/{data_source_id}/query", json=filter_body or {})
            if response.status_code >= 400:
                raise NotionError(f"NOTION_{response.status_code}", "Notion rejected the query")
            body = cast(dict[str, Any], response.json())
            return cast(list[dict[str, Any]], body.get("results", []))
        except httpx.TimeoutException as exc:
            raise NotionError("NOTION_TIMEOUT", "Notion API request timed out") from exc
        except httpx.TransportError as exc:
            raise NotionError("NOTION_NETWORK", "Notion API network error") from exc

    async def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        try:
            response = await self._client.get(f"/data_sources/{data_source_id}")
            if response.status_code >= 400:
                raise NotionError(f"NOTION_{response.status_code}", "Notion rejected the schema request")
            return cast(dict[str, Any], response.json())
        except httpx.TimeoutException as exc:
            raise NotionError("NOTION_TIMEOUT", "Notion API request timed out") from exc
        except httpx.TransportError as exc:
            raise NotionError("NOTION_NETWORK", "Notion API network error") from exc

    async def search(self, query: str, page_size: int = 10) -> NotionPage:
        try:
            response = await self._client.post("/search", json={"query": query, "page_size": page_size})
            if response.status_code >= 400:
                raise NotionError(f"NOTION_{response.status_code}", "Notion rejected the search")
            body = cast(dict[str, Any], response.json())
            return NotionPage(
                cast(list[dict[str, Any]], body.get("results", [])),
                bool(body.get("has_more", False)),
                cast(str | None, body.get("next_cursor")),
            )
        except httpx.TimeoutException as exc:
            raise NotionError("NOTION_TIMEOUT", "Notion API request timed out") from exc
        except httpx.TransportError as exc:
            raise NotionError("NOTION_NETWORK", "Notion API network error") from exc
