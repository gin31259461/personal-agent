from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.query import ListTasksArgs
from personal_agent.schemas.task import CreateTaskArgs

from .client import NotionClient, NotionError
from .mapping import (
    date_range_property,
    merge,
    multi_select_property,
    number_property,
    paragraph_blocks,
    people_property,
    relation_property,
    rich_text_property,
    select_property,
    status_property,
    title_property,
)
from .relations import RelationResolver

MAX_DESCRIPTION_LENGTH = 2000


def _description_text(note: str | None, body: str | None) -> str | None:
    value = (note or body or "").strip()
    if not value:
        return None
    if len(value) <= MAX_DESCRIPTION_LENGTH:
        return value
    return value[: MAX_DESCRIPTION_LENGTH - 1].rstrip() + "…"


class TaskService:
    def __init__(
        self,
        client: NotionClient,
        data_source_id: str,
        properties: dict[str, str],
        resolver: RelationResolver | None = None,
        project_data_source_id: str | None = None,
    ) -> None:
        self.client, self.data_source_id, self.properties = client, data_source_id, properties
        self.resolver = resolver
        self.project_data_source_id = project_data_source_id

    async def create(self, args: CreateTaskArgs, external_id: str | None = None) -> ToolResult:
        p = self.properties
        properties = merge(title_property(p["title"], args.title))
        description = _description_text(args.description, None)
        if args.due_at:
            properties.update(date_range_property(p.get("due", p.get("due_date", "Due")), args.due_at, args.due_end_at))
        if args.status and p.get("status"):
            properties.update(status_property(p["status"], args.status))
        if args.priority:
            properties.update(status_property(p["priority"], args.priority.capitalize()))
        description_property = p.get("description") or p.get("note")
        if description and description_property:
            properties.update(rich_text_property(description_property, description))
        if external_id and p.get("external_id"):
            properties.update(rich_text_property(p["external_id"], external_id))
        try:
            if args.project and self.resolver and self.project_data_source_id and p.get("project"):
                project = await self.resolver.resolve(self.project_data_source_id, "Name", args.project)
                properties.update(relation_property(p["project"], [project.id]))
            if args.parent_task and self.resolver and p.get("parent_task"):
                parent = await self.resolver.resolve(self.data_source_id, p["title"], args.parent_task)
                properties.update(relation_property(p["parent_task"], [parent.id]))
            if args.assignee_user_ids and p.get("assignee"):
                properties.update(people_property(p["assignee"], args.assignee_user_ids))
            if args.smart_list and p.get("smart_list"):
                properties.update(select_property(p["smart_list"], args.smart_list))
            if args.recur_interval is not None and p.get("recur_interval"):
                from decimal import Decimal

                properties.update(number_property(p["recur_interval"], Decimal(args.recur_interval)))
            if args.recur_unit and p.get("recur_unit"):
                properties.update(select_property(p["recur_unit"], args.recur_unit))
            if args.recur_days and p.get("recur_days"):
                properties.update(multi_select_property(p["recur_days"], args.recur_days))
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
