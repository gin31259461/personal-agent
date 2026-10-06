import argparse
import asyncio
from pathlib import Path

from personal_agent import __version__
from personal_agent.agent.runtime import AgentRuntime
from personal_agent.config import ApplicationConfig, NotionUserDatabases, Settings
from personal_agent.context import current_discord_user_id
from personal_agent.discord.bot import PersonalAgentBot
from personal_agent.discord.handler import MessageAuthorizer
from personal_agent.llm.client import LLMClient
from personal_agent.schemas.common import ToolResult
from personal_agent.schemas.expense import AddExpenseArgs, AddTransactionArgs
from personal_agent.schemas.query import (
    GetDatabaseInfoArgs,
    ListTasksArgs,
    QueryExpensesArgs,
    SearchNotionArgs,
)
from personal_agent.schemas.task import CreateTaskArgs
from personal_agent.storage.db import Database
from personal_agent.tools.base import RegisteredTool, ToolRisk
from personal_agent.tools.executor import ToolExecutor
from personal_agent.tools.notion.client import NotionClient
from personal_agent.tools.notion.finance import FinanceService
from personal_agent.tools.notion.relations import RelationResolver
from personal_agent.tools.notion.schema import NotionSchemaCache
from personal_agent.tools.notion.search import NotionSearchService
from personal_agent.tools.notion.tasks import TaskService
from personal_agent.tools.policy import Policy
from personal_agent.tools.registry import ToolRegistry


def _create_user_services(
    notion: NotionClient,
    resolver: RelationResolver,
    databases: NotionUserDatabases,
    schema_cache: NotionSchemaCache | None = None,
) -> tuple[TaskService, FinanceService, NotionSearchService]:
    task_properties = dict(databases.tasks.properties)
    tasks = TaskService(
        notion,
        databases.tasks.data_source_id,
        task_properties,
        resolver,
        databases.projects.data_source_id if databases.projects else None,
        schema_cache=schema_cache,
    )
    finance_properties = dict(databases.finance.properties)
    finance = FinanceService(
        notion,
        databases.finance.data_source_id,
        finance_properties,
        resolver,
        databases.categories.data_source_id if databases.categories else None,
        databases.accounts.data_source_id if databases.accounts else None,
        schema_cache=schema_cache,
    )
    sources: dict[str, tuple[str, str | None]] = {
        "tasks": (databases.tasks.data_source_id, task_properties.get("title")),
        "transactions": (databases.finance.data_source_id, finance_properties.get("title")),
    }
    for alias, source in (
        ("projects", databases.projects),
        ("categories", databases.categories),
        ("accounts", databases.accounts),
    ):
        if source:
            sources[alias] = (source.data_source_id, source.properties.get("title"))
    search = NotionSearchService(notion, sources, schema_cache=schema_cache)
    return tasks, finance, search


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


async def _get_database_info(
    settings: Settings,
    schema_cache: NotionSchemaCache,
    args: GetDatabaseInfoArgs,
) -> ToolResult:
    try:
        user_id = current_discord_user_id.get()
        user_dbs = settings.notion.get_for_user(user_id) or settings.notion.default
        if not user_dbs:
            return ToolResult.fail("NO_DATABASES", "No Notion databases configured")

        db_alias = args.database.lower().strip()
        ds_id: str | None = None
        if db_alias in {"finance", "transactions", "expense", "expenses"}:
            ds_id = user_dbs.finance.data_source_id
        elif db_alias in {"tasks", "task"}:
            ds_id = user_dbs.tasks.data_source_id
        elif db_alias in {"categories", "category"}:
            if user_dbs.categories:
                ds_id = user_dbs.categories.data_source_id
            else:
                ds_id = await schema_cache.get_relation_target_data_source_id(user_dbs.finance.data_source_id, "Category")
        elif db_alias in {"accounts", "account"}:
            if user_dbs.accounts:
                ds_id = user_dbs.accounts.data_source_id
            else:
                ds_id = await schema_cache.get_relation_target_data_source_id(user_dbs.finance.data_source_id, "Account")
        elif db_alias in {"projects", "project"}:
            if user_dbs.projects:
                ds_id = user_dbs.projects.data_source_id
            else:
                ds_id = await schema_cache.get_relation_target_data_source_id(user_dbs.tasks.data_source_id, "Project")

        if not ds_id:
            return ToolResult.fail("DATABASE_NOT_FOUND", f"Could not find or resolve database '{args.database}'")

        if args.property:
            result = await schema_cache.get_property_options(ds_id, args.property)
            return ToolResult.ok(result)

        if db_alias in {"categories", "category", "accounts", "account", "projects", "project"}:
            options = await schema_cache.get_relation_options(ds_id)
            return ToolResult.ok({"database": args.database, "options": [opt["name"] for opt in options]})

        summary = await schema_cache.get_database_summary(ds_id)
        return ToolResult.ok(summary)
    except Exception as exc:
        return ToolResult.fail("DATABASE_INFO_ERROR", str(exc))


def build_runtime(settings: Settings) -> AgentRuntime:
    notion = NotionClient(settings.notion_token.get_secret_value())
    schema_cache = NotionSchemaCache(notion)
    resolver = RelationResolver(notion, schema_cache=schema_cache)

    user_services: dict[str, tuple[TaskService, FinanceService, NotionSearchService]] = {}
    default_services: tuple[TaskService, FinanceService, NotionSearchService] | None = None

    if settings.notion.default is not None:
        default_services = _create_user_services(notion, resolver, settings.notion.default, schema_cache)

    for user_id, user_dbs in settings.notion.users.items():
        user_services[user_id] = _create_user_services(notion, resolver, user_dbs, schema_cache)

    def resolve_services() -> tuple[TaskService, FinanceService, NotionSearchService]:
        user_id = current_discord_user_id.get()
        if user_id and user_id in user_services:
            return user_services[user_id]
        if default_services is not None:
            return default_services
        raise RuntimeError(f"No Notion databases configured for user {user_id}")

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            "notion_create_task",
            "Create a task in the user's Tasks database.",
            CreateTaskArgs,
            lambda args: _create_task(resolve_services()[0], args),
            ToolRisk.WRITE_SAFE,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_add_transaction",
            "Add an income or expense transaction.",
            AddTransactionArgs,
            lambda args: _add_transaction(resolve_services()[1], args),
            ToolRisk.WRITE_SAFE,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_search",
            "Search configured Notion databases by title.",
            SearchNotionArgs,
            lambda args: resolve_services()[2].search(args),
            ToolRisk.READ,
        )
    )
    closers = [notion.close]
    registry.register(
        RegisteredTool(
            "notion_list_tasks",
            "List tasks from the user's Tasks database.",
            ListTasksArgs,
            lambda args: _list_tasks(resolve_services()[0], args),
            ToolRisk.READ,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_query_expenses",
            "Query expenses from the user's Finance database.",
            QueryExpensesArgs,
            lambda args: _query_expenses(resolve_services()[1], args),
            ToolRisk.READ,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_add_expense",
            "Add an expense to the user's Finance database.",
            AddExpenseArgs,
            lambda args: _add_expense(resolve_services()[1], args),
            ToolRisk.WRITE_SAFE,
        )
    )
    registry.register(
        RegisteredTool(
            "notion_get_database_info",
            "Inspect a Notion database schema or list available options for a property (categories, accounts, statuses).",
            GetDatabaseInfoArgs,
            lambda args: _get_database_info(settings, schema_cache, args),
            ToolRisk.READ,
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
