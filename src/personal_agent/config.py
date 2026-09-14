from pathlib import Path
from typing import Annotated, Any, cast

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    timezone: str = "Asia/Taipei"
    max_tool_iterations: Annotated[int, Field(gt=0, le=20)] = 5
    database_url: str = "sqlite+aiosqlite:///./agent.db"


class DiscordSettings(BaseModel):
    guild_id: int
    channel_id: int
    owner_user_ids: list[int] = Field(default_factory=list)
    owner_user_id: int | None = None

    @model_validator(mode="after")
    def normalize_owner_user_ids(self) -> "DiscordSettings":
        if not self.owner_user_ids and self.owner_user_id is not None:
            self.owner_user_ids = [self.owner_user_id]
        if not self.owner_user_ids:
            raise ValueError("discord.owner_user_ids must contain at least one user ID")
        self.owner_user_ids = list(dict.fromkeys(self.owner_user_ids))
        return self


class LLMSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "Qwen3.6-35B-A3B"
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.2
    max_tokens: Annotated[int, Field(gt=0)] = 4096
    timeout_seconds: Annotated[float, Field(gt=0)] = 60


class NotionDatabaseSettings(BaseModel):
    data_source_id: str
    properties: dict[str, str] = {}


class NotionSettings(BaseModel):
    tasks: NotionDatabaseSettings
    finance: NotionDatabaseSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app: AppSettings
    discord: DiscordSettings
    llm: LLMSettings = LLMSettings()
    notion: NotionSettings
    discord_token: str
    notion_token: str

    @classmethod
    def from_toml(cls, path: Path, env_file: Path | None = None) -> "Settings":
        import tomllib

        with path.open("rb") as file:
            values = tomllib.load(file)
        settings_type = cast(Any, cls)
        return cast(Settings, settings_type(_env_file=env_file, **values))
