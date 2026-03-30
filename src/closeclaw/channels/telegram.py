"""Telegram bot channel – bridges Telegram messages to the agent loop."""

from __future__ import annotations

from loguru import logger
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from closeclaw.agent_core.loop import AgentSession, ToolCallDone, ToolCallStart, TurnDone
from closeclaw.config import Settings

# Per-user agent sessions (keyed by Telegram user ID).
_sessions: dict[int, AgentSession] = {}


def _get_session(user_id: int, settings: Settings) -> AgentSession:
    if user_id not in _sessions:
        _sessions[user_id] = AgentSession(settings)
    return _sessions[user_id]


def _is_allowed(user_id: int, settings: Settings) -> bool:
    ids = settings.allowed_user_ids
    if not ids:
        return True  # empty list = allow everyone
    return user_id in ids


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
    _sessions.pop(user_id, None)
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

    session = _get_session(user_id, settings)

    # Send "typing" indicator
    await update.effective_chat.send_action(ChatAction.TYPING)

    # Collect full response
    parts: list[str] = []
    async for event in session.chat(text):
        if isinstance(event, ToolCallStart):
            parts.append(f"🔧 `{event.name}`")
        elif isinstance(event, ToolCallDone):
            status = "✅" if not event.is_error else "❌"
            preview = event.output[:200]
            parts.append(f"{status} ```\n{preview}\n```")
        elif isinstance(event, TurnDone):
            if event.text:
                parts.append(event.text)

    reply = "\n".join(parts) or "(no response)"

    # Telegram message limit is 4096 chars
    if len(reply) > 4000:
        reply = reply[:4000] + "\n… (truncated)"

    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


# ── Entry point ───────────────────────────────────────────────────────────────


def run_telegram_bot(settings: Settings) -> None:
    """Build and run the Telegram bot (blocking)."""
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Please set it in .env or as an environment variable."
        )

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("reset", _cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    logger.info("Starting Telegram bot …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
