from pathlib import Path
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AppSettings(StrictModel):
    timezone: str = "Asia/Taipei"
    max_tool_iterations: Annotated[int, Field(gt=0, le=20)] = 5
    database_url: str = "sqlite+aiosqlite:///./agent.db"
    clarification_ttl_seconds: Annotated[int, Field(gt=0, le=86400)] = 600
    instructions_path: Path | None = None
    instructions_max_bytes: Annotated[int, Field(gt=0, le=1048576)] = 32768


class DiscordSettings(StrictModel):
    guild_id: Annotated[int, Field(gt=0)]
    channel_id: Annotated[int, Field(gt=0)]
    owner_user_ids: list[Annotated[int, Field(gt=0)]]

    @model_validator(mode="after")
    def normalize_owner_user_ids(self) -> "DiscordSettings":
        if not self.owner_user_ids:
            raise ValueError("discord.owner_user_ids must contain at least one user ID")
        self.owner_user_ids = list(dict.fromkeys(self.owner_user_ids))
        return self


class LLMSettings(StrictModel):
    base_url: HttpUrl = HttpUrl("http://127.0.0.1:8080/v1")
    model: str = "Qwen3.6-35B-A3B"
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.2
    max_tokens: Annotated[int, Field(gt=0)] = 4096
    timeout_seconds: Annotated[float, Field(gt=0)] = 60


class NotionDatabaseSettings(StrictModel):
    data_source_id: Annotated[str, Field(min_length=1)]
    properties: dict[str, str] = {}


class NotionSettings(StrictModel):
    tasks: NotionDatabaseSettings
    finance: NotionDatabaseSettings
    projects: NotionDatabaseSettings | None = None
    categories: NotionDatabaseSettings | None = None
    accounts: NotionDatabaseSettings | None = None


class WebSearchSettings(StrictModel):
    enabled: bool = False
    provider: Literal["searxng"] = "searxng"
    base_url: HttpUrl = HttpUrl("http://127.0.0.1:8888")
    timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 15
    max_results: Annotated[int, Field(gt=0, le=25)] = 10
    max_response_bytes: Annotated[int, Field(gt=1024, le=1048576)] = 262144


class RuntimeCapabilities(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PERSONAL_AGENT_", extra="ignore", hide_input_in_errors=True)

    web_search_url: HttpUrl | None = None


class ApplicationConfig(StrictModel):
    app: AppSettings
    discord: DiscordSettings
    llm: LLMSettings = LLMSettings()
    notion: NotionSettings
    web_search: WebSearchSettings = WebSearchSettings()

    @classmethod
    def from_toml(cls, path: Path) -> "ApplicationConfig":
        import tomllib

        with path.open("rb") as file:
            return cls.model_validate(tomllib.load(file))


class RuntimeSecrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    discord_token: SecretStr
    notion_token: SecretStr


class Settings(ApplicationConfig):
    discord_token: SecretStr
    notion_token: SecretStr
    web_search_url: HttpUrl | None = None

    @classmethod
    def from_toml(cls, path: Path, env_file: Path | None = None) -> "Settings":
        config = ApplicationConfig.from_toml(path)
        secrets_type = cast(Any, RuntimeSecrets)
        secrets = cast(RuntimeSecrets, secrets_type(_env_file=env_file))
        capabilities_type = cast(Any, RuntimeCapabilities)
        capabilities = cast(RuntimeCapabilities, capabilities_type(_env_file=env_file))
        data = config.model_dump() | secrets.model_dump() | capabilities.model_dump()
        settings = cls.model_validate(data)
        if (
            settings.web_search_url is not None
            and settings.web_search.enabled
            and str(settings.web_search_url).rstrip("/") != str(settings.web_search.base_url).rstrip("/")
        ):
            raise ValueError("web search environment and legacy config URLs conflict")
        return settings
