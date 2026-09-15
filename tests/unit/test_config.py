from pathlib import Path

import pytest
from pydantic import ValidationError

from personal_agent.config import ApplicationConfig, Settings

MINIMAL_CONFIG = """
[app]
timezone = "Asia/Taipei"

[discord]
guild_id = 3
channel_id = 2
owner_user_ids = [1, 1, 4]

[notion.tasks]
data_source_id = "tasks"

[notion.finance]
data_source_id = "finance"
"""


def write(path: Path, value: str) -> Path:
    path.write_text(value)
    return path


def test_application_config_rejects_unknown_fields(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", MINIMAL_CONFIG + "\nunknown = true\n")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ApplicationConfig.from_toml(path)


def test_application_config_normalizes_authorized_users(tmp_path: Path) -> None:
    config = ApplicationConfig.from_toml(write(tmp_path / "config.toml", MINIMAL_CONFIG))
    assert config.discord.owner_user_ids == [1, 4]


def test_runtime_settings_load_secrets_without_exposing_them(tmp_path: Path) -> None:
    config = write(tmp_path / "config.toml", MINIMAL_CONFIG)
    env = write(tmp_path / ".env", "DISCORD_TOKEN=discord-private\nNOTION_TOKEN=notion-private\n")
    settings = Settings.from_toml(config, env)
    assert settings.discord_token.get_secret_value() == "discord-private"
    assert "discord-private" not in repr(settings)
    assert "notion-private" not in repr(settings)


def test_runtime_settings_require_both_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    config = write(tmp_path / "config.toml", MINIMAL_CONFIG)
    env = write(tmp_path / ".env", "DISCORD_TOKEN=synthetic-private\n")
    with pytest.raises(ValidationError) as raised:
        Settings.from_toml(config, env)
    assert "synthetic-private" not in str(raised.value)


def test_runtime_web_search_url_enables_managed_capability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAL_AGENT_WEB_SEARCH_URL", "http://127.0.0.1:8888")
    config = write(tmp_path / "config.toml", MINIMAL_CONFIG)
    env = write(tmp_path / ".env", "DISCORD_TOKEN=discord\nNOTION_TOKEN=notion\n")
    settings = Settings.from_toml(config, env)
    assert str(settings.web_search_url) == "http://127.0.0.1:8888/"


def test_managed_and_legacy_web_search_urls_must_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONAL_AGENT_WEB_SEARCH_URL", "http://127.0.0.1:8888")
    config = write(
        tmp_path / "config.toml",
        MINIMAL_CONFIG + '\n[web_search]\nenabled = true\nbase_url = "http://127.0.0.1:9999"\n',
    )
    env = write(tmp_path / ".env", "DISCORD_TOKEN=discord\nNOTION_TOKEN=notion\n")
    with pytest.raises(ValueError, match="URLs conflict"):
        Settings.from_toml(config, env)
