"""Webhook FastAPI per il Telegram Bot.

Questo modulo si integra con l'app FastAPI principale
per ricevere webhook da Telegram.
"""

from fastapi import APIRouter, Request, HTTPException

from mes_system.telegram_bot.bot import ProductionBot, TelegramConfig
from mes_system.config import settings

router = APIRouter()

# Il bot viene inizializzato al primo webhook
_bot: ProductionBot | None = None


def get_bot() -> ProductionBot:
    """Lazy init del bot Telegram."""
    global _bot
    if _bot is None:
        import os
        _bot = ProductionBot(TelegramConfig(
            bot_token=os.environ.get("MES_TELEGRAM_BOT_TOKEN", ""),
            openai_api_key=os.environ.get("MES_OPENAI_API_KEY"),
            anthropic_api_key=os.environ.get("MES_ANTHROPIC_API_KEY"),
        ))
    return _bot


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Riceve update da Telegram via webhook."""
    bot = get_bot()
    if not bot.config.bot_token:
        raise HTTPException(status_code=503, detail="Telegram bot non configurato")

    update = await request.json()
    await bot.handle_update(update)
    return {"ok": True}
