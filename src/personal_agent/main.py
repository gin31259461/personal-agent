import argparse
import asyncio
from pathlib import Path

from personal_agent import __version__
from personal_agent.agent.runtime import AgentRuntime
from personal_agent.config import ApplicationConfig, Settings
from personal_agent.discord.bot import PersonalAgentBot
from personal_agent.discord.handler import MessageAuthorizer
from personal_agent.llm.client import LLMClient
from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs, AddTransactionArgs
from personal_agent.schemas.query import ListTasksArgs, QueryExpensesArgs, SearchNotionArgs, WebSearchArgs
from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.storage.db import Database
from personal_agent.tools.base import RegisteredTool, ToolRisk
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.notion.client import NotionClient
from personal_agent.tools.notion.finance import FinanceService
from personal_agent.tools.notion.relations import RelationResolver
from personal_agent.tools.notion.search import NotionSearchService
from personal_agent.tools.notion.tasks import TaskService
from personal_agent.tools.policy import Policy
from personal_agent.tools.registry import ToolRegistry
from personal_agent.tools.web_search import SearxngSearchService


async def _create_task(service: TaskService, args: CreateTaskArgs) -> ToolResult:
    return await service.create(args)


async def _add_expense(service: FinanceService, args: AddExpenseArgs) -> ToolResult:
    return await service.add(args)


async def _add_transaction(service: FinanceService, args: AddTransactionArgs) -> ToolResult:
    return await service.add_transaction(args)


async def _list_tasks(service: TaskService, args: ListTasksArgs) -> ToolResult:
    return await service.list(args)


async def _query_expenses(service: FinanceService, args: QueryExpensesArgs) -> ToolResult:
    return await service.query(args)


def build_runtime(settings: Settings) -> AgentRuntime:
    notion = NotionClient(settings.notion_token.get_secret_value())
    resolver = RelationResolver(notion)
    tasks = TaskService(
        notion,
        settings.notion.tasks.data_source_id,
        settings.notion.tasks.properties,
        resolver,
        settings.notion.projects.data_source_id if settings.notion.projects else None,
    )
    finance = FinanceService(
        notion,
        settings.notion.finance.data_source_id,
        settings.notion.finance.properties,
        resolver,
        settings.notion.categories.data_source_id if settings.notion.categories else None,
        settings.notion.accounts.data_source_id if settings.notion.accounts else None,
    )
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
            "notion_add_transaction",
            "Add an income or expense transaction.",
            AddTransactionArgs,
            lambda args: _add_transaction(finance, args),
            ToolRisk.WRITE_SAFE,
        )
    )
    sources = {
        "tasks": (settings.notion.tasks.data_source_id, settings.notion.tasks.properties.get("title", "Name")),
        "transactions": (settings.notion.finance.data_source_id, settings.notion.finance.properties.get("title", "Item Name")),
    }
    for alias, source, title in (
        ("projects", settings.notion.projects, "Name"),
        ("categories", settings.notion.categories, "Category Name"),
        ("accounts", settings.notion.accounts, "Account Name"),
    ):
        if source:
            sources[alias] = (source.data_source_id, source.properties.get("title", title))
    notion_search = NotionSearchService(notion, sources)
    registry.register(
        RegisteredTool(
            "notion_search",
            "Search configured Notion databases by title.",
            SearchNotionArgs,
            notion_search.search,
            ToolRisk.READ,
        )
    )
    closers = [notion.close]
    web_search_url = settings.web_search_url or (settings.web_search.base_url if settings.web_search.enabled else None)
    if web_search_url is not None:
        web_search = SearxngSearchService(
            str(web_search_url),
            settings.web_search.timeout_seconds,
            settings.web_search.max_results,
            settings.web_search.max_response_bytes,
        )
        registry.register(
            RegisteredTool(
                "web_search", "Search the public web and return cited results.", WebSearchArgs, web_search.search, ToolRisk.READ
            )
        )
        closers.append(web_search.close)
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
        str(settings.llm.base_url),
        settings.llm.model,
        settings.llm.temperature,
        settings.llm.max_tokens,
        settings.llm.timeout_seconds,
    )
    closers.append(llm.close)
    default_preferences = Path(__file__).parent / "agent" / "default_preferences.md"
    instructions_path = settings.app.instructions_path or default_preferences
    raw = instructions_path.read_bytes()
    if len(raw) > settings.app.instructions_max_bytes:
        raise ValueError("instructions file exceeds configured size limit")
    preferences = raw.decode("utf-8")
    return AgentRuntime(
        llm,
        registry,
        ToolExecutor(registry, Policy()),
        settings.app.timezone,
        settings.app.max_tool_iterations,
        preferences,
        closers,
        settings.app.clarification_ttl_seconds,
    )


async def run(settings: Settings) -> None:
    database = Database(settings.app.database_url)
    await database.create_schema()
    runtime = build_runtime(settings)
    bot = PersonalAgentBot(
        settings.discord_token.get_secret_value(),
        MessageAuthorizer(settings.discord.guild_id, settings.discord.channel_id, settings.discord.owner_user_ids),
        runtime,
        database,
    )
    try:
        await bot.start(settings.discord_token.get_secret_value())
    finally:
        await runtime.close()
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--config", type=Path, default=Path("config.toml"))
    run_parser.add_argument("--env-file", type=Path)
    config_parser = commands.add_parser("check-config")
    config_parser.add_argument("--config", type=Path, required=True)
    runtime_parser = commands.add_parser("check-runtime")
    runtime_parser.add_argument("--config", type=Path, required=True)
    runtime_parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    if args.command == "check-config":
        ApplicationConfig.from_toml(args.config)
        print("Personal Agent configuration is valid")
        return
    env_file = args.env_file if args.env_file and args.env_file.exists() else None
    settings = Settings.from_toml(args.config, env_file)
    if args.command == "check-runtime":
        print("Personal Agent runtime configuration is valid")
        return
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
