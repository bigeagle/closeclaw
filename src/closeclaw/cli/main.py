"""Click CLI – debug chat and Telegram launcher."""

from __future__ import annotations

import asyncio
import sys

import click
from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from closeclaw.config import get_settings

console = Console()


def _setup_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<level>{message}</level>")
    if verbose:
        logger.enable("kosong")


# ── CLI group ─────────────────────────────────────────────────────────────────


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """CloseClaw – AI Agent on Telegram."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _setup_logging(verbose)


# ── chat command (debug REPL) ─────────────────────────────────────────────────


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Interactive chat with the agent (debug / development)."""
    asyncio.run(_chat_loop())


async def _chat_loop() -> None:
    from closeclaw.agent_core.loop import (
        AgentSession,
        TextDelta,
        ToolCallDone,
        ToolCallStart,
        TurnDone,
    )

    settings = get_settings()

    if not settings.kimi_api_key:
        console.print("[red]Error:[/red] KIMI_API_KEY is not set.")
        raise SystemExit(1)

    session = AgentSession(settings)
    console.print(
        Panel("CloseClaw Debug Chat  (type [bold]exit[/bold] or Ctrl-C to quit)"),
    )

    while True:
        try:
            user_input = console.input("[bold green]You>[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye!")
            break

        if user_input.strip().lower() in {"exit", "quit"}:
            break
        if not user_input.strip():
            continue

        console.print()
        streamed_text = ""
        in_streaming = False

        async for event in session.chat(user_input):
            if isinstance(event, TextDelta):
                # Stream text token-by-token to stdout
                if not in_streaming:
                    in_streaming = True
                print(event.text, end="", flush=True)
                streamed_text += event.text
            elif isinstance(event, ToolCallStart):
                if in_streaming:
                    print()  # newline after streamed text
                    in_streaming = False
                console.print(
                    f"  [dim]🔧 calling [cyan]{event.name}[/cyan][/dim]",
                )
                if event.arguments:
                    console.print(f"  [dim]{event.arguments[:200]}[/dim]")
            elif isinstance(event, ToolCallDone):
                icon = "✅" if not event.is_error else "❌"
                preview = event.output[:300].rstrip()
                console.print(f"  [dim]{icon} {preview}[/dim]")
                console.print()
                streamed_text = ""  # reset for next step
            elif isinstance(event, TurnDone):
                if in_streaming:
                    print()  # final newline
                    in_streaming = False

        console.print()


# ── gateway command (full agent bot) ─────────────────────────────────────────


@cli.command()
@click.pass_context
def gateway(ctx: click.Context) -> None:
    """Start the Telegram bot with the full agent loop."""
    from closeclaw.channels.telegram import run_telegram_bot

    settings = get_settings()

    if not settings.kimi_api_key:
        console.print("[red]Error:[/red] KIMI_API_KEY is not set.")
        raise SystemExit(1)
    if not settings.telegram_bot_token:
        console.print("[red]Error:[/red] TELEGRAM_BOT_TOKEN is not set.")
        raise SystemExit(1)

    console.print("[green]Starting Telegram gateway …[/green]")
    run_telegram_bot(settings)


# ── telegram command (debug bot) ─────────────────────────────────────────────


@cli.command()
@click.pass_context
def telegram(ctx: click.Context) -> None:
    """Run a minimal Telegram debug bot (echo, ping, draft test)."""
    from closeclaw.channels.telegram import run_telegram_debug

    settings = get_settings()

    if not settings.telegram_bot_token:
        console.print("[red]Error:[/red] TELEGRAM_BOT_TOKEN is not set.")
        raise SystemExit(1)

    console.print("[green]Starting Telegram debug bot …[/green]")
    run_telegram_debug(settings)


# ── version command ───────────────────────────────────────────────────────────


@cli.command()
def version() -> None:
    """Show version."""
    from closeclaw import __version__

    console.print(f"closeclaw {__version__}")
