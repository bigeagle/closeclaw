"""Telegram bot channel – bridges Telegram messages to the agent loop."""

from __future__ import annotations

import asyncio
import html

from loguru import logger
from telegramify_markdown import markdownify
from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from closeclaw.agent_core.loop import (
    AgentSession,
    ImageOutput,
    TextDelta,
)
from closeclaw.config import Settings

# Per-chat agent sessions (keyed by Telegram chat ID).
_sessions: dict[int, AgentSession] = {}

TG_MSG_LIMIT = 4096


def _get_session(chat_id: int, settings: Settings) -> AgentSession:
    if chat_id not in _sessions:
        _sessions[chat_id] = AgentSession(settings, chat_id=chat_id)
    return _sessions[chat_id]


def _is_allowed(user_id: int, settings: Settings) -> bool:
    ids = settings.allowed_user_ids
    if not ids:
        return True
    return user_id in ids


def _truncate(text: str, limit: int = TG_MSG_LIMIT - 96) -> str:
    if len(text) > limit:
        return text[:limit] + "\n… (truncated)"
    return text


def _format_sender(user) -> str:
    """Format a Telegram User into an escaped display name."""
    if user is None:
        return "unknown"
    name = html.escape(user.full_name)
    if user.username:
        name += f" (@{html.escape(user.username)})"
    return name


def _format_user_message(update: Update) -> str:
    """Wrap user text with sender metadata in XML."""
    assert update.message and update.effective_user
    sender = _format_sender(update.effective_user)
    timestamp = update.message.date.astimezone().isoformat()
    text = update.message.text or ""

    parts: list[str] = []
    reply = update.message.reply_to_message
    if reply:
        reply_sender = _format_sender(reply.from_user)
        reply_ts = reply.date.astimezone().isoformat()
        reply_text = reply.text or reply.caption or "(non-text message)"
        if len(reply_text) > 500:
            reply_text = reply_text[:500] + "…"
        parts.append(
            f'<reply_to sender="{reply_sender}" timestamp="{reply_ts}">\n'
            f"{reply_text}\n"
            f"</reply_to>"
        )
    parts.append(text)

    body = "\n".join(parts)
    return f'<message sender="{sender}" timestamp="{timestamp}">\n{body}\n</message>'


async def _send_photo(bot, chat_id: int, event: ImageOutput) -> None:
    """Send an image file as a Telegram photo message."""
    try:
        caption_text = None
        parse_mode = None
        if event.caption:
            try:
                caption_text = markdownify(event.caption)
                parse_mode = ParseMode.MARKDOWN_V2
            except Exception:
                caption_text = event.caption
        with open(event.path, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption_text,
                parse_mode=parse_mode,
            )
    except Exception as exc:
        logger.warning("send_photo failed: {e}", e=exc)


# ── Handlers ──────────────────────────────────────────────────────────────────


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_chat
    await update.effective_chat.send_message(
        "👋 Hi! I'm *CloseClaw*, an AI assistant. Send me a message!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.effective_user and update.effective_chat
    user_id = update.effective_user.id
    settings: Settings = context.bot_data["settings"]
    if not _is_allowed(user_id, settings):
        return
    _sessions.pop(update.effective_chat.id, None)
    await update.effective_chat.send_message("🔄 Session reset.")


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message and update.effective_user and update.effective_chat
    settings: Settings = context.bot_data["settings"]
    user_id = update.effective_user.id

    if not _is_allowed(user_id, settings):
        logger.info("Ignored message from unauthorised user {uid}", uid=user_id)
        return

    text = update.message.text or ""
    if not text.strip():
        return

    logger.info("[TG] user={uid} msg={text}", uid=user_id, text=text[:80])

    user_message = _format_user_message(update)
    session = _get_session(update.effective_chat.id, settings)
    await _stream_reply(update, context, session, user_message)


# ── Streaming reply via edit-message ──────────────────────────────────────────


async def _stream_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AgentSession,
    text: str,
) -> None:
    """Stream reply by sending a message then editing it as tokens arrive."""
    assert update.message and update.effective_chat
    chat_id = update.effective_chat.id

    accumulated = ""
    message_id: int | None = None

    async def _keep_typing() -> None:
        """Re-send typing action every 5s until cancelled."""
        try:
            while True:
                await update.effective_chat.send_action(ChatAction.TYPING)  # type: ignore[union-attr]
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    typing_task = asyncio.create_task(_keep_typing())
    last_edit = 0.0
    throttle = 1.5  # seconds between edits (Telegram rate-limit safe)

    async def _maybe_edit() -> None:
        nonlocal message_id, last_edit
        now = asyncio.get_event_loop().time()
        if now - last_edit < throttle:
            return
        display = _truncate(accumulated)
        if not display:
            return
        try:
            if message_id is None:
                msg = await update.message.reply_text(display)  # type: ignore[union-attr]
                message_id = msg.message_id
            else:
                await context.bot.edit_message_text(
                    text=display,
                    chat_id=chat_id,
                    message_id=message_id,
                )
            last_edit = asyncio.get_event_loop().time()
        except Exception as exc:
            logger.debug("edit_message_text failed: {e}", e=exc)

    async for event in session.chat(text):
        if isinstance(event, TextDelta):
            accumulated += event.text
            await _maybe_edit()
        elif isinstance(event, ImageOutput):
            await _send_photo(context.bot, chat_id, event)

    # Final edit with complete text
    display = _truncate(accumulated) if accumulated else "(no response)"
    try:
        mdv2 = markdownify(display)
        if message_id is None:
            await update.message.reply_text(  # type: ignore[union-attr]
                mdv2, parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await context.bot.edit_message_text(
                text=mdv2,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception:
        try:
            if message_id is None:
                await update.message.reply_text(display)  # type: ignore[union-attr]
            else:
                await context.bot.edit_message_text(
                    text=display,
                    chat_id=chat_id,
                    message_id=message_id,
                )
        except Exception:
            pass
    finally:
        typing_task.cancel()


# ── Entry point ───────────────────────────────────────────────────────────────


def run_telegram_debug(settings: Settings) -> None:
    """Run a minimal debug bot for testing Telegram connectivity."""
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    app = Application.builder().token(settings.telegram_bot_token).build()

    async def _cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message
        await update.message.reply_text("🛠 Debug bot is running!")

    async def _cmd_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message
        await update.message.reply_text("pong 🏓")

    async def _cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message and update.effective_user and update.effective_chat
        u = update.effective_user
        c = update.effective_chat
        lines = [
            f"user_id:   {u.id}",
            f"username:  @{u.username}" if u.username else "username:  (none)",
            f"chat_id:   {c.id}",
            f"chat_type: {c.type}",
        ]
        await update.message.reply_text("\n".join(lines))

    async def _echo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message
        await update.message.reply_text(_format_user_message(update))

    async def _cmd_md(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a Markdown test message to check rendering."""
        assert update.message
        sample = (
            "**Bold text** and _italic text_\n"
            "`inline code` and \n\n"
            "```python\nprint('hello')\n```\n"
            "[link](https://example.com)\n"
            "- bullet one\n- bullet two\n"
            "> blockquote line\n"
            "1. numbered\n2. list\n"
            "---\n"
            "**nested _bold italic_** end"
        )
        # Try telegramify-markdown
        try:
            mdv2 = markdownify(f"📝 telegramify-markdown:\n\n{sample}")
            await update.message.reply_text(mdv2, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as exc:
            await update.message.reply_text(f"❌ telegramify-markdown failed: {exc}")

    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("ping", _cmd_ping))
    app.add_handler(CommandHandler("info", _cmd_info))
    app.add_handler(CommandHandler("md", _cmd_md))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _echo))

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Start the debug bot"),
                BotCommand("ping", "Connectivity check"),
                BotCommand("info", "Show user / chat info"),
                BotCommand("md", "Test Markdown rendering"),
            ]
        )

    app.post_init = _post_init
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def run_telegram_bot(settings: Settings) -> None:
    """Build and run the Telegram bot (blocking)."""
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Please set it in .env or as an environment variable."
        )

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("reset", _cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Start chatting"),
                BotCommand("reset", "Reset conversation history"),
            ]
        )

    app.post_init = _post_init
    app.run_polling(allowed_updates=Update.ALL_TYPES)
