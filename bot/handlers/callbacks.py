import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback queries de botões inline (uso futuro)."""
    query = update.callback_query
    await query.answer()
    logger.info(f"Callback recebido: {query.data}")
