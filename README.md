# Personal Agent

Personal Discord assistant backed by an OpenAI-compatible llama-swap endpoint and Notion. Discord messages are authorized by guild, channel, and user IDs. The model can only call explicitly registered tools; Pydantic validates tool arguments and SQLite records processed Discord events.

## Current capabilities

- Create Notion tasks with title, optional description, due date, priority, and Markdown page body.
- Add expenses, list tasks, and query expenses through registered Notion tools.
- Show `Pending`, `Done`, and `Failed` status in Discord while a request is processed.
- Restrict requests to configured Discord users in one guild and channel.
- Convert supported Markdown headings, lists, checkboxes, quotes, code blocks, emphasis, inline code, and links into Notion blocks.

## Development

Requirements: Python 3.13 and `uv`.

```bash
uv sync --locked
cp config.example.toml config.toml
cp .env.example .env
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

Run locally after filling `config.toml` and `.env`:

```bash
uv run personal-agent --config ./config.toml --env-file ./.env
```

The environment file contains `DISCORD_TOKEN` and `NOTION_TOKEN`. Never commit it.

## Configuration

`config.toml` contains non-secret runtime configuration. Important sections:

```toml
[discord]
guild_id = 123456789
channel_id = 123456789
owner_user_ids = [123456789]

[notion.tasks.properties]
title = "Name"
description = "Description"
due_date = "Due"
priority = "Priority"
```

`owner_user_ids` may contain multiple Discord user IDs. The task tool uses structured output: `description` is a short optional summary and `body` is the optional full Markdown content. If no description is supplied, the Notion Description property remains empty; if no body is supplied, no page body blocks are added.

## Arch Linux deployment

The installer creates the `personal-agent` service account, installs the managed Python runtime in a service-readable path, synchronizes the locked environment, installs the systemd unit, and starts the service.

Prepare `config.toml` and `.env` beside `install.sh`, then run:

```bash
sudo ./install.sh
```

The installer preserves existing production configuration and `/var/lib/personal-agent`. It stores configuration in `/etc/personal-agent/` and runtime SQLite state in `/var/lib/personal-agent/`.

Useful operations:

```bash
sudo systemctl status personal-agent.service
sudo systemctl restart personal-agent.service
sudo journalctl -u personal-agent.service -f
```

Remove the service and application files while retaining configuration and state:

```bash
sudo ./uninstall.sh
```

Use `sudo ./uninstall.sh --purge` only when configuration and runtime state should also be removed.

## Architecture

```text
Discord message
  -> guild/channel/user authorization
  -> event idempotency claim in SQLite
  -> LLM tool call
  -> registry lookup and Pydantic validation
  -> policy evaluation
  -> Notion adapter
  -> final LLM response
  -> Discord status message update
```

Tokens are kept at the configuration boundary. The model receives registered tool schemas, not credentials or arbitrary network/filesystem access.
