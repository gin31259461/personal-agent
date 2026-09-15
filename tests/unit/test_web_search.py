import httpx
import pytest

from personal_agent.schemas.query import WebSearchArgs
from personal_agent.tools.web_search import SearxngSearchService


@pytest.mark.asyncio
async def test_web_search_returns_bounded_results():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"results": [{"title": "Result", "url": "https://example.com", "content": "Summary"}]}
        )
    )
    client = httpx.AsyncClient(transport=transport)
    service = SearxngSearchService("http://search", 1, 5, client=client)
    result = await service.search(WebSearchArgs(query="latest documentation"))
    assert result.success is True
    assert result.data["results"][0]["url"] == "https://example.com"
    await client.aclose()
