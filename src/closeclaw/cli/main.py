"""Click CLI – debug chat and Telegram launcher."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from closeclaw.config import get_settings

console = Console()


def _setup_logging(verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    fmt = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"
    logger.add(sys.stderr, level=level, format=fmt)
    if verbose:
        logger.enable("kosong")


# ── CLI group ─────────────────────────────────────────────────────────────────


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(dir_okay=False),
    default="~/.closeclaw/config.yaml",
    show_default=True,
    help="Path to config.yaml.",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config_file: str) -> None:
    """CloseClaw – AI Agent on Telegram."""
    load_dotenv(Path.cwd() / ".env")
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["config_file"] = str(Path(config_file).expanduser())
    _setup_logging(verbose)


# ── chat command (debug REPL) ─────────────────────────────────────────────────


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Interactive chat with the agent (debug / development)."""
    asyncio.run(_chat_loop(ctx.obj.get("config_file")))


async def _chat_loop(config_file: str | None = None) -> None:
    from closeclaw.agent_core.loop import (
        AgentSession,
        ImageOutput,
        TextDelta,
        ToolCallDone,
        ToolCallStart,
        TurnDone,
    )

    settings = get_settings(config_file=config_file)

    if not settings.kimi_api_key:
        logger.error("KIMI_API_KEY is not set.")
        raise SystemExit(1)

    session = AgentSession(settings)
    console.print(
        Panel("CloseClaw Debug Chat  (type [bold]exit[/bold] or Ctrl-C to quit)"),
    )

    while True:
        try:
            user_input = console.input("[bold green]You>[/bold green] ")
        except EOFError, KeyboardInterrupt:
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
            elif isinstance(event, ImageOutput):
                if in_streaming:
                    print()
                    in_streaming = False
                console.print(f"  [dim]🖼️  Image: {event.path}[/dim]")
                if event.caption:
                    console.print(f"  [dim]   {event.caption}[/dim]")
            elif isinstance(event, TurnDone):
                if in_streaming:
                    print()  # final newline
                    in_streaming = False

        console.print()


# ── gateway command (full agent bot) ─────────────────────────────────────────


@cli.command()
@click.option("--debug", is_flag=True, help="Set log level to DEBUG.")
@click.pass_context
def gateway(ctx: click.Context, debug: bool) -> None:
    """Start the Telegram bot with the full agent loop."""
    if debug:
        _setup_logging(verbose=True)
    from closeclaw.api import run_gateway

    settings = get_settings(config_file=ctx.obj.get("config_file"))

    if not settings.kimi_api_key:
        logger.error("KIMI_API_KEY is not set.")
        raise SystemExit(1)
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        raise SystemExit(1)

    logger.info("Starting gateway …")
    run_gateway(settings)


# ── telegram command (debug bot) ─────────────────────────────────────────────


@cli.command()
@click.pass_context
def telegram(ctx: click.Context) -> None:
    """Run a minimal Telegram debug bot (echo, ping, draft test)."""
    from closeclaw.channels.telegram import run_telegram_debug

    settings = get_settings(config_file=ctx.obj.get("config_file"))

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        raise SystemExit(1)

    logger.info("Starting Telegram debug bot …")
    run_telegram_debug(settings)


# ── heartbeat command ─────────────────────────────────────────────────────


@cli.command()
@click.option("-p", "--prompt", default="", help="Override the heartbeat prompt.")
@click.pass_context
def heartbeat(ctx: click.Context, prompt: str) -> None:
    """Trigger a heartbeat on the running gateway."""
    import json
    import urllib.request

    settings = get_settings(config_file=ctx.obj.get("config_file"))
    port = settings.api_port
    if not port:
        console.print("[red]api_port is not configured.[/red]")
        raise SystemExit(1)
    url = f"http://127.0.0.1:{port}/heartbeat"
    body = json.dumps({"prompt": prompt}).encode() if prompt else b"{}"
    req = urllib.request.Request(
        url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            console.print(f"[green]Heartbeat triggered ({resp.status})[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to reach gateway: {exc}[/red]")
        raise SystemExit(1)


# ── version command ───────────────────────────────────────────────────────────


@cli.command()
def version() -> None:
    """Show version."""
    from closeclaw import __version__

    console.print(f"closeclaw {__version__}")
