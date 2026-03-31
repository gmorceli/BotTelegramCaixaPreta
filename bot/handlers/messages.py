import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.storage.database import Database

logger = logging.getLogger(__name__)


def create_message_handler(db: Database):
    """Cria handler passivo que captura todas as mensagens de texto em grupos."""

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Ignora mensagens privadas
        if update.effective_chat.type not in ("group", "supergroup"):
            return

        # Ignora mensagens sem texto
        if not update.message or not update.message.text:
            return

        # Ignora comandos (são tratados por outros handlers)
        if update.message.text.startswith("/"):
            return

        chat_id = update.effective_chat.id

        # Verifica se o grupo está configurado
        group = await db.get_group(chat_id)
        if not group:
            return

        reply_to = None
        if update.message.reply_to_message:
            reply_to = update.message.reply_to_message.message_id

        await db.save_message(
            chat_id=chat_id,
            user_id=update.effective_user.id,
            username=update.effective_user.username,
            display_name=update.effective_user.full_name,
            message_text=update.message.text,
            telegram_message_id=update.message.message_id,
            reply_to=reply_to,
        )

    return handle_message
