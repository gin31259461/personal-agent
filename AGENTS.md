# AGENTS Instructions

## Scope

This repository contains a single-host Discord assistant. Discord is the transport, llama-swap is the OpenAI-compatible inference endpoint, Notion stores business data, and SQLite stores runtime state and idempotency records.

## Source of truth

- Runtime behavior is defined by `src/personal_agent/`.
- Dependency constraints are defined by `pyproject.toml`; `uv.lock` fixes the Python dependency graph used by uv2nix and local uv development.
- `config.example.toml` documents configuration shape. Production configuration lives outside the repository at `/etc/personal-agent/config.toml`.
- `.env`, `/etc/personal-agent/agent.env`, tokens, and database files are sensitive; never print, commit, or include their values in logs or tests.

## Safety boundaries

- Keep Discord guild, channel, and user authorization enforced by `MessageAuthorizer`.
- Add capabilities through the explicit tool registry and validate arguments with Pydantic schemas.
- Do not add arbitrary shell, filesystem, HTTP, or Notion capabilities to the LLM.
- Treat Notion writes and external model calls as side effects. Use fakes or mock transports in tests.
- Do not delete `/var/lib/personal-agent` or production configuration while changing code.

## Testing

Keep tests focused on behavior that protects the product contract: schemas, authorization and status replies, LLM response parsing, tool-loop serialization, policy decisions, and Notion task mapping. Avoid tests that only restate trivial helpers or implementation details.

Run before handoff:

```bash
uv sync --locked
uv run pytest -q
uv run ruff check src tests
uv run mypy src
nix flake check --show-trace --print-build-logs
nix build --no-link --show-trace --print-build-logs .#personal-agent
git diff --check
```

## Documentation

Update `README.md` when public behavior, configuration, deployment, or validation commands change. Keep operational instructions in the README concise and keep implementation history out of repository documentation.
