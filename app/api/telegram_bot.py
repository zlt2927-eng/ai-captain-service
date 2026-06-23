"""Telegram bot integration for Digital Captain using long polling."""

import logging
from typing import Any

from fastapi import FastAPI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)

CONFIRM_ORDER_CALLBACK = "confirm_order"
CANCEL_ORDER_CALLBACK = "cancel_order"
DEFAULT_RESTAURANT_ID = "default_restaurant"


def create_telegram_application(settings: Settings) -> Application:
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_handler(
        CallbackQueryHandler(handle_callback_query, pattern=f"^({CONFIRM_ORDER_CALLBACK}|{CANCEL_ORDER_CALLBACK})$")
    )
    return application


def _should_render_action_buttons(response: dict[str, Any], assistant_text: str) -> bool:
    if response.get("cart_snapshot") is not None:
        return True

    normalized_text = assistant_text.strip().lower()
    if not normalized_text:
        return False

    keywords = ["checkout", "confirm", "تأكيد", "دفع", "طلب", "إتمام"]
    return any(keyword in normalized_text for keyword in keywords)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        return

    chat_id = update.effective_chat.id if update.effective_chat else update.message.chat.id
    session_id = str(chat_id)
    user_message = update.message.text.strip()

    gemini_orchestrator: GeminiOrchestrator = context.application.bot_data["gemini_orchestrator"]
    session_service: SessionService = context.application.bot_data["session_service"]
    http_client: HTTPClient = context.application.bot_data["http_client"]

    try:
        response = await gemini_orchestrator.process_message(
            restaurant_id=DEFAULT_RESTAURANT_ID,
            session_id=session_id,
            user_message=user_message,
        )
    except Exception as exc:
        logger.exception("Telegram message processing failed")
        await update.message.reply_text(
            "عذراً، حدث خطأ داخلي أثناء معالجة طلبك. حاول مرة أخرى لاحقاً."
        )
        return

    assistant_text = response.get("assistant_text", "").strip()
    reply_markup = None
    if _should_render_action_buttons(response, assistant_text):
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("تأكيد الطلب ✅", callback_data=CONFIRM_ORDER_CALLBACK),
                    InlineKeyboardButton("إلغاء الطلب ❌", callback_data=CANCEL_ORDER_CALLBACK),
                ]
            ]
        )

    await update.message.reply_text(
        assistant_text or "عذراً، لم أتمكن من معالجة طلبك الآن.",
        reply_markup=reply_markup,
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    if query.data == CONFIRM_ORDER_CALLBACK:
        await query.edit_message_text("تم تأكيد طلبك بنجاح!")
    elif query.data == CANCEL_ORDER_CALLBACK:
        await query.edit_message_text("تم إلغاء الطلب وتصفير السلة")
    else:
        await query.edit_message_text("تم استلام ردك. شكراً لك.")


async def initialize_telegram_bot(app: FastAPI) -> Application:
    settings: Settings = app.state.settings
    telegram_app = create_telegram_application(settings)

    telegram_app.bot_data["settings"] = settings
    telegram_app.bot_data["http_client"] = app.state.http_client
    telegram_app.bot_data["session_service"] = app.state.session_service
    telegram_app.bot_data["gemini_orchestrator"] = app.state.gemini_orchestrator

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    logger.info("Telegram bot polling started")
    return telegram_app


async def shutdown_telegram_bot(telegram_app: Application) -> None:
    await telegram_app.updater.stop_polling()
    await telegram_app.stop()
    await telegram_app.shutdown()
    logger.info("Telegram bot polling stopped")
