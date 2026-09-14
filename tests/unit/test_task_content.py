import pytest

from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.tools.notion.tasks import TaskService


class FakeNotion:
    def __init__(self):
        self.properties = None
        self.children = None

    async def create_page(self, data_source_id, properties, children=None):
        self.properties = properties
        self.children = children
        return {"id": "page-id"}


@pytest.mark.asyncio
async def test_long_task_content_is_written_to_page_body():
    notion = FakeNotion()
    service = TaskService(notion, "source-id", {"title": "Name", "due_date": "Due"})
    result = await service.create(CreateTaskArgs(title="整理伺服器", description="更新套件", body="1. 更新套件\n2. 檢查服務"))
    assert result.success is True
    assert result.data["body_written"] is True
    assert [
        block["numbered_list_item"]["rich_text"][0]["text"]["content"] for block in notion.children
    ] == ["更新套件", "檢查服務"]


@pytest.mark.asyncio
async def test_description_is_written_without_creating_a_body():
    notion = FakeNotion()
    service = TaskService(notion, "source-id", {"title": "Name", "description": "Description"})

    result = await service.create(CreateTaskArgs(title="整理伺服器", description="更新套件並檢查服務"))

    assert result.success is True
    assert notion.properties["Description"] == {"rich_text": [{"text": {"content": "更新套件並檢查服務"}}]}
    assert notion.children is None


@pytest.mark.asyncio
async def test_description_is_omitted_when_not_provided():
    notion = FakeNotion()
    service = TaskService(notion, "source-id", {"title": "Name", "description": "Description"})

    result = await service.create(CreateTaskArgs(title="整理伺服器"))

    assert result.success is True
    assert "Description" not in notion.properties


@pytest.mark.asyncio
async def test_description_and_body_are_written_to_separate_destinations():
    notion = FakeNotion()
    service = TaskService(notion, "source-id", {"title": "Name", "description": "Description"})

    result = await service.create(
        CreateTaskArgs(title="整理伺服器", description="更新伺服器套件", body="**更新套件**\n- 檢查服務")
    )

    assert result.success is True
    assert notion.properties["Description"]["rich_text"][0]["text"]["content"] == "更新伺服器套件"
    assert notion.children[0]["type"] == "paragraph"
    assert notion.children[0]["paragraph"]["rich_text"][0]["annotations"]["bold"] is True
    assert notion.children[1]["type"] == "bulleted_list_item"


@pytest.mark.asyncio
async def test_description_and_body_remain_within_their_own_limits():
    notion = FakeNotion()
    service = TaskService(notion, "source-id", {"title": "Name", "description": "Description"})
    body = "x" * 20000

    result = await service.create(CreateTaskArgs(title="長任務", description="長任務摘要", body=body))

    assert result.success is True
    description = notion.properties["Description"]["rich_text"][0]["text"]["content"]
    assert description == "長任務摘要"
    assert notion.children[0]["paragraph"]["rich_text"][0]["text"]["content"] == body
