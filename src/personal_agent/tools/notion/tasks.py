from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.query import ListTasksArgs
from personal_agent.schemas.task import CreateTaskArgs

from .client import NotionClient, NotionError
from .mapping import date_property, merge, paragraph_blocks, rich_text_property, status_property, title_property

MAX_DESCRIPTION_LENGTH = 2000


def _description_text(note: str | None, body: str | None) -> str | None:
    value = (note or body or "").strip()
    if not value:
        return None
    if len(value) <= MAX_DESCRIPTION_LENGTH:
        return value
    return value[: MAX_DESCRIPTION_LENGTH - 1].rstrip() + "…"


class TaskService:
    def __init__(self, client: NotionClient, data_source_id: str, properties: dict[str, str]) -> None:
        self.client, self.data_source_id, self.properties = client, data_source_id, properties

    async def create(self, args: CreateTaskArgs, external_id: str | None = None) -> ToolResult:
        p = self.properties
        properties = merge(title_property(p["title"], args.title))
        description = _description_text(args.description, None)
        if args.due_at:
            properties.update(date_property(p["due_date"], args.due_at))
        if args.priority:
            properties.update(status_property(p["priority"], args.priority.capitalize()))
        description_property = p.get("description") or p.get("note")
        if description and description_property:
            properties.update(rich_text_property(description_property, description))
        if external_id and p.get("external_id"):
            properties.update(rich_text_property(p["external_id"], external_id))
        try:
            page = await self.client.create_page(
                self.data_source_id,
                properties,
                paragraph_blocks(args.body) if args.body else None,
            )
            return ToolResult.ok(
                {
                    "task_id": page.get("id", ""),
                    "title": args.title,
                    "due_at": args.due_at.isoformat() if args.due_at else None,
                    "body_written": bool(args.body),
                }
            )
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))

    async def list(self, args: ListTasksArgs) -> ToolResult:
        body = {}
        if args.status:
            body["filter"] = {"property": self.properties["status"], "status": {"equals": args.status}}
        try:
            pages = await self.client.query_data_source(self.data_source_id, body)
            tasks = [{"id": page.get("id", ""), "url": page.get("url", "")} for page in pages]
            return ToolResult.ok({"tasks": tasks, "count": len(tasks)})
        except NotionError as exc:
            return ToolResult.fail(exc.code, str(exc))
