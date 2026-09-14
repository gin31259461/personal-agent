import argparse
import asyncio
from pathlib import Path

from personal_agent.agent.runtime import AgentRuntime
from personal_agent.config import Settings
from personal_agent.discord.bot import PersonalAgentBot
from personal_agent.discord.handler import MessageAuthorizer
from personal_agent.llm.client import LLMClient
from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs
from personal_agent.schemas.query import ListTasksArgs, QueryExpensesArgs
from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.storage.db import Database
from personal_agent.tools.base import RegisteredTool, ToolRisk
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.notion.client import NotionClient
from personal_agent.tools.notion.finance import FinanceService
from personal_agent.tools.notion.tasks import TaskService
from personal_agent.tools.policy import Policy
from personal_agent.tools.registry import ToolRegistry


async def _create_task(service: TaskService, args: CreateTaskArgs) -> ToolResult:
    return await service.create(args)


async def _add_expense(service: FinanceService, args: AddExpenseArgs) -> ToolResult:
    return await service.add(args)


async def _list_tasks(service: TaskService, args: ListTasksArgs) -> ToolResult:
    return await service.list(args)


async def _query_expenses(service: FinanceService, args: QueryExpensesArgs) -> ToolResult:
    return await service.query(args)


def build_runtime(settings: Settings) -> AgentRuntime:
    notion = NotionClient(settings.notion_token)
    tasks = TaskService(notion, settings.notion.tasks.data_source_id, settings.notion.tasks.properties)
    finance = FinanceService(notion, settings.notion.finance.data_source_id, settings.notion.finance.properties)
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            "notion_create_task",
            "Create a task in the user's Tasks database.",
            CreateTaskArgs,
            lambda args: _create_task(tasks, args),
            ToolRisk.WRITE_SAFE,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_list_tasks",
            "List tasks from the user's Tasks database.",
            ListTasksArgs,
            lambda args: _list_tasks(tasks, args),
            ToolRisk.READ,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_query_expenses",
            "Query expenses from the user's Finance database.",
            QueryExpensesArgs,
            lambda args: _query_expenses(finance, args),
            ToolRisk.READ,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_add_expense",
            "Add an expense to the user's Finance database.",
            AddExpenseArgs,
            lambda args: _add_expense(finance, args),
            ToolRisk.WRITE_SAFE,
        )
    )
    llm = LLMClient(
        settings.llm.base_url, settings.llm.model, settings.llm.temperature, settings.llm.max_tokens, settings.llm.timeout_seconds
    )
    return AgentRuntime(llm, registry, ToolExecutor(registry, Policy()), settings.app.timezone, settings.app.max_tool_iterations)


async def run(settings: Settings) -> None:
    database = Database(settings.app.database_url)
    await database.create_schema()
    runtime = build_runtime(settings)
    bot = PersonalAgentBot(
        settings.discord_token,
        MessageAuthorizer(settings.discord.guild_id, settings.discord.channel_id, settings.discord.owner_user_ids),
        runtime,
        database,
    )
    try:
        await bot.start(settings.discord_token)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    env_file = args.env_file if args.env_file.exists() else None
    settings = Settings.from_toml(args.config, env_file)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
