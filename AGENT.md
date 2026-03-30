# CloseClaw

AI Agent on Telegram, powered by Kimi (Moonshot).

## Project Structure

```
src/closeclaw/
├── __init__.py              # Package root, version
├── config.py                # pydantic-settings configuration
├── agent_core/              # LLM agent loop (kosong-based)
│   ├── __init__.py
│   ├── loop.py              # AgentSession & event-driven agent loop
│   └── tools/
│       ├── __init__.py
│       └── bash.py          # Bash shell tool
├── channels/
│   ├── __init__.py
│   └── telegram.py          # Telegram bot (python-telegram-bot)
└── cli/
    ├── __init__.py
    └── main.py              # Click CLI: chat, telegram, version
```

## Setup

```bash
uv sync
cp .env .env.local   # fill in KIMI_API_KEY and TELEGRAM_BOT_TOKEN
```

## Configuration

All config is managed via `pydantic-settings` in `src/closeclaw/config.py`.
Values are read from `.env` file and can be overridden by environment variables.

| Variable                  | Description                         | Required |
|---------------------------|-------------------------------------|----------|
| `KIMI_API_KEY`            | Moonshot / Kimi API key             | Yes      |
| `KIMI_BASE_URL`           | API base URL                        | No       |
| `KIMI_MODEL`              | Model name (default: `kimi-k2.5`)   | No       |
| `TELEGRAM_BOT_TOKEN`      | Telegram Bot API token              | For TG   |
| `TELEGRAM_ALLOWED_USERS`  | Comma-separated Telegram user IDs   | No       |

## CLI Commands

```bash
closeclaw chat              # Interactive debug REPL
closeclaw telegram          # Start Telegram bot
closeclaw version           # Show version
closeclaw -v chat           # Verbose / debug logging
```

## Key Dependencies

- **kosong** – LLM abstraction layer (agent step loop, tool dispatch)
- **pydantic-settings** – Typed configuration from .env / env vars
- **python-telegram-bot** – Async Telegram Bot API
- **click** – CLI framework
- **loguru** + **rich** – Logging and terminal output

## Coding Conventions

- Python 3.13+, async-first (`asyncio`).
- `from __future__ import annotations` in all modules.
- Agent events use dataclasses (`AgentEvent` hierarchy in `loop.py`).
- Tools extend `kosong.tooling.CallableTool2[Params]`.
