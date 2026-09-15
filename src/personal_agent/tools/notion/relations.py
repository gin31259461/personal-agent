from dataclasses import dataclass
from typing import Any

from personal_agent.schemas.task import RelationRef

from .client import NotionClient, NotionError


class RelationResolutionError(NotionError):
    pass


@dataclass(frozen=True)
class ResolvedRelation:
    id: str
    name: str


def _title(page: dict[str, Any], property_name: str) -> str:
    value = page.get("properties", {}).get(property_name, {}).get("title", [])
    return "".join(item.get("plain_text", "") for item in value).strip()


class RelationResolver:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    async def resolve(self, data_source_id: str, title_property: str, reference: RelationRef) -> ResolvedRelation:
        if reference.id:
            return ResolvedRelation(reference.id, reference.id)
        assert reference.name is not None
        pages = await self.client.query_data_source(
            data_source_id,
            {"filter": {"property": title_property, "title": {"equals": reference.name}}, "page_size": 6},
        )
        matches = [(str(page.get("id", "")), _title(page, title_property)) for page in pages]
        matches = [(page_id, name) for page_id, name in matches if name.casefold() == reference.name.casefold()]
        if not matches:
            raise RelationResolutionError("RELATION_NOT_FOUND", f"找不到 relation：{reference.name}")
        if len(matches) > 1:
            names = "、".join(name for _, name in matches[:5])
            raise RelationResolutionError("RELATION_AMBIGUOUS", f"Relation 不唯一：{names}")
        return ResolvedRelation(*matches[0])
