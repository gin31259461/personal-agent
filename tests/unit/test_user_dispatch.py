from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from personal_agent.config import Settings
from personal_agent.context import current_discord_user_id
from personal_agent.main import build_runtime

MULTI_USER_CONFIG = """
[app]
timezone = "Asia/Taipei"

[discord]
guild_id = 1
channel_id = 2
owner_user_ids = [100, 200]

[notion.default.tasks]
data_source_id = "default-tasks-ds"

[notion.default.finance]
data_source_id = "default-finance-ds"

[notion.users."100".tasks]
data_source_id = "user100-tasks-ds"

[notion.users."100".finance]
data_source_id = "user100-finance-ds"
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    config_file = tmp_path / "config.toml"
    config_file.write_text(MULTI_USER_CONFIG)
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=fake-token\nNOTION_TOKEN=fake-notion-token\n")
    return Settings.from_toml(config_file, env_file)


@pytest.mark.asyncio
async def test_user_dispatch_routes_to_user_specific_data_source(settings: Settings):
    with patch("personal_agent.main.NotionClient") as mock_client_cls, patch("personal_agent.main.LLMClient") as mock_llm_cls:
        mock_client = mock_client_cls.return_value
        mock_client.create_page = AsyncMock(return_value={"id": "page-123"})
        mock_client.close = AsyncMock()

        mock_llm = mock_llm_cls.return_value
        mock_llm.close = AsyncMock()

        runtime = build_runtime(settings)

        # 1. Execute task creation for user 100
        current_discord_user_id.set("100")
        result_user100 = await runtime.executor.execute(
            "notion_create_task", {"title": "Task for User 100"}
        )
        assert result_user100.success is True
        # Verify the data_source_id used in create_page was user100's
        mock_client.create_page.assert_called_with(
            "user100-tasks-ds",
            {"Name": {"title": [{"text": {"content": "Task for User 100"}}]}},
            None,
        )

        # 2. Execute task creation for user 200 (fallback to default)
        current_discord_user_id.set("200")
        result_user200 = await runtime.executor.execute(
            "notion_create_task", {"title": "Task for User 200"}
        )
        assert result_user200.success is True
        # Verify the data_source_id used was default
        mock_client.create_page.assert_called_with(
            "default-tasks-ds",
            {"Name": {"title": [{"text": {"content": "Task for User 200"}}]}},
            None,
        )

        # 3. Execute notion_search for user 100
        mock_client.query_data_source = AsyncMock(
            return_value=[
                {
                    "id": "p1",
                    "url": "https://notion.so/p1",
                    "properties": {"Name": {"title": [{"text": {"content": "Found"}}]}},
                }
            ]
        )
        current_discord_user_id.set("100")
        search_result = await runtime.executor.execute(
            "notion_search", {"query": "test"}
        )
        assert search_result.success is True
        # Ensure it queried user 100's databases, not default's
        queried_ds_ids = [call[0][0] for call in mock_client.query_data_source.call_args_list]
        assert "user100-tasks-ds" in queried_ds_ids
        assert "user100-finance-ds" in queried_ds_ids
        assert "default-tasks-ds" not in queried_ds_ids

        await runtime.close()
