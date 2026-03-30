"""Telegram bot channel – bridges Telegram messages to the agent loop."""

from __future__ import annotations

import asyncio

from loguru import logger
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
    TextDelta,
)
from closeclaw.config import Settings

# Per-user agent sessions (keyed by Telegram user ID).
_sessions: dict[int, AgentSession] = {}

# Module-level draft_id counter (monotonically increasing, wraps at INT32 max).
_DRAFT_ID_MAX = 2_147_483_647
_next_draft_id: int = 0

# Minimum interval (seconds) between sendMessageDraft calls isn't needed—
# we use a signal-driven loop so network RTT naturally throttles.

TG_MSG_LIMIT = 4096


def _allocate_draft_id() -> int:
    global _next_draft_id
    _next_draft_id = 1 if _next_draft_id >= _DRAFT_ID_MAX else _next_draft_id + 1
    return _next_draft_id


def _get_session(user_id: int, settings: Settings) -> AgentSession:
    if user_id not in _sessions:
        _sessions[user_id] = AgentSession(settings)
    return _sessions[user_id]


def _is_allowed(user_id: int, settings: Settings) -> bool:
    ids = settings.allowed_user_ids
    if not ids:
        return True
    return user_id in ids


def _truncate(text: str, limit: int = TG_MSG_LIMIT - 96) -> str:
    if len(text) > limit:
        return text[:limit] + "\n… (truncated)"
    return text


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
    is_private = update.effective_chat.type == "private"

    if is_private:
        await _stream_reply_draft(update, context, session, text)
    else:
        await _stream_reply_edit(update, context, session, text)


# ── Private chat: sendMessageDraft streaming ─────────────────────────────────


async def _stream_reply_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AgentSession,
    text: str,
) -> None:
    """Stream reply via sendMessageDraft (private chats only)."""
    assert update.message and update.effective_chat
    chat_id = update.effective_chat.id
    bot = context.bot

    draft_id = _allocate_draft_id()
    accumulated = ""
    last_sent = ""
    done = False
    text_changed = asyncio.Event()

    async def _sender_loop() -> None:
        """Signal-driven loop: wake on new tokens, RTT naturally throttles."""
        nonlocal last_sent
        while not done:
            await text_changed.wait()
            text_changed.clear()
            current = accumulated
            if current and current != last_sent:
                draft_text = _truncate(current)
                try:
                    await bot.send_message_draft(
                        chat_id=chat_id,
                        draft_id=draft_id,
                        text=draft_text,
                    )
                    last_sent = current
                except Exception as exc:
                    logger.debug("sendMessageDraft failed: {e}", e=exc)

    sender_task = asyncio.create_task(_sender_loop())

    try:
        async for event in session.chat(text):
            if isinstance(event, TextDelta):
                accumulated += event.text
                text_changed.set()
    finally:
        done = True
        text_changed.set()
        await sender_task

    # Clear the draft bubble, then send a real message.
    try:
        await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text="⏳")
    except Exception:
        pass

    reply = _truncate(accumulated) if accumulated else "(no response)"
    try:
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text(reply)


# ── Group chat: sendMessage + editMessageText fallback ───────────────────────


async def _stream_reply_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: AgentSession,
    text: str,
) -> None:
    """Stream reply via edit-message fallback (group chats)."""
    assert update.message and update.effective_chat
    chat_id = update.effective_chat.id

    await update.effective_chat.send_action(ChatAction.TYPING)

    accumulated = ""
    message_id: int | None = None
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

    # Final edit with complete text
    display = _truncate(accumulated) if accumulated else "(no response)"
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

    async def _cmd_draft(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Test sendMessageDraft streaming."""
        assert update.message and update.effective_chat
        chat_id = update.effective_chat.id
        draft_id = _allocate_draft_id()
        text = ""
        for word in "Hello this is a streaming draft test ✅".split():
            text += (" " if text else "") + word
            try:
                await ctx.bot.send_message_draft(
                    chat_id=chat_id,
                    draft_id=draft_id,
                    text=text,
                )
            except Exception as exc:
                logger.warning("draft test failed: {e}", e=exc)
                await update.message.reply_text(f"❌ sendMessageDraft failed: {exc}")
                return
            await asyncio.sleep(0.4)
        await update.message.reply_text(text)

    async def _echo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message
        await update.message.reply_text(f"echo: {update.message.text}")

    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("ping", _cmd_ping))
    app.add_handler(CommandHandler("info", _cmd_info))
    app.add_handler(CommandHandler("draft", _cmd_draft))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _echo))

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Start the debug bot"),
                BotCommand("ping", "Connectivity check"),
                BotCommand("info", "Show user / chat info"),
                BotCommand("draft", "Test sendMessageDraft streaming"),
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
