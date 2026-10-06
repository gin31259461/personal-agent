# Personal Agent

Personal Discord assistant backed by an OpenAI-compatible llama-swap endpoint and Notion. Discord messages are authorized by guild, channel, and user IDs. The model can only call explicitly registered tools; Pydantic validates tool arguments and SQLite records processed Discord events.

## Current capabilities

- Create Notion tasks with title, optional description, due date, priority, and Markdown page body.
- Add expenses, list tasks, and query expenses through registered Notion tools.
- Show animated thinking status in Discord while a tool request is processed.
- Restrict requests to configured Discord users in one guild and channel.
- Convert supported Markdown headings, lists, checkboxes, quotes, code blocks, emphasis, inline code, and links into Notion blocks.
- Resolve Task projects and transaction categories/accounts through validated Notion relations.
- Search configured Notion data sources.

## Nix package

The flake builds the application and its exact `uv.lock` dependency graph with
uv2nix. Production does not create a virtual environment or resolve packages at
runtime.

```bash
nix flake check --show-trace --print-build-logs
nix build --no-link --show-trace --print-build-logs .#personal-agent
```

The flake exposes `packages.x86_64-linux.personal-agent` and a default development
shell. Host configuration, systemd ownership and runtime files deliberately remain
outside this application repository.

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
uv run --env-file ./.env personal-agent run --config ./config.toml
```

The environment file contains `DISCORD_TOKEN` and `NOTION_TOKEN`. Never commit it. Model preferences default to
`personal_agent/agent/default_preferences.md`; set `app.instructions_path` to load an external UTF-8 file at startup.

Normal conversation uses Discord's typing indicator and receives a direct reply. A visible animated thinking status is only
created after the model requests a tool; it is updated with the final reply or `Failed` status. Multi-turn conversation context is preserved
per-channel in SQLite with a 2-hour sliding window. Structured clarification state expires after
`app.clarification_ttl_seconds` and handles missing relation or argument retries.

## Configuration

`config.toml` contains non-secret runtime configuration. Important sections:

```toml
[discord]
guild_id = 123456789
channel_id = 123456789
owner_user_ids = [123456789]

[notion.tasks]
data_source_id = "default-tasks-id"

[notion.finance]
data_source_id = "default-finance-id"

# Optional per-user Notion overrides
[notion.users."123456789".tasks]
data_source_id = "user-specific-tasks-id"
```

`owner_user_ids` may contain multiple Discord user IDs. Each authorized user can optionally be mapped to their own Notion databases under `[notion.users."<id>"]`; if omitted, the global default Notion databases are used. The task tool uses structured output: `description` is a short optional summary and `body` is the optional full Markdown content. If no description is supplied, the Notion Description property remains empty; if no body is supplied, no page body blocks are added.

## Deployment contract

The production host owns the `personal-agent` account, systemd unit and runtime
directories. It supplies `/etc/personal-agent/config.toml`, exposes
`DISCORD_TOKEN` and `NOTION_TOKEN` in the process environment, and keeps SQLite
state under `/var/lib/personal-agent`. Those mutable files and credentials never
enter this repository or the Nix store.

Validate a prepared configuration without contacting external services:

```bash
personal-agent check-config --config /etc/personal-agent/config.toml
personal-agent check-runtime --config /etc/personal-agent/config.toml
```

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
