import logging
from datetime import time

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.config import Config
from bot.storage.database import Database
from bot.services.claude_service import ClaudeService
from bot.services.summary_service import SummaryService
from bot.handlers.commands import create_command_handlers
from bot.handlers.messages import create_message_handler
from bot.handlers.callbacks import handle_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Inicializa banco de dados e registra comandos."""
    from telegram import BotCommand

    db: Database = application.bot_data["db"]
    await db.initialize()
    logger.info("Database PostgreSQL inicializado")

    # Registra comandos para autocomplete no Telegram
    commands = [
        BotCommand("setup", "Configurar grupo (admin)"),
        BotCommand("resumo", "Gerar resumo das discussões"),
        BotCommand("decisao", "Registrar uma decisão"),
        BotCommand("decisoes", "Listar decisões registradas"),
        BotCommand("excluirdecisao", "Excluir decisão (admin)"),
        BotCommand("pendencia", "Criar pendência"),
        BotCommand("pendencias", "Listar pendências abertas"),
        BotCommand("feito", "Marcar pendência como concluída"),
        BotCommand("excluirpendencia", "Excluir pendência (admin)"),
        BotCommand("contexto", "Perguntar sobre o projeto"),
        BotCommand("buscar", "Pesquisar na web"),
        BotCommand("status", "Status do projeto (admin)"),
        BotCommand("help", "Ver comandos disponíveis"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Comandos registrados no Telegram")


async def post_shutdown(application):
    """Fecha banco de dados ao parar o bot."""
    db: Database = application.bot_data["db"]
    await db.close()
    logger.info("Database fechado")


def main():
    if not Config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
    if not Config.DATABASE_URL:
        raise ValueError("DATABASE_URL não configurado")
    if not Config.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY não configurado")

    # Inicializa serviços
    db = Database(Config.DATABASE_URL)
    claude = ClaudeService()
    summary_service = SummaryService(db, claude)

    # Cria aplicação
    app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # Armazena referências nos bot_data
    app.bot_data["db"] = db
    app.bot_data["claude"] = claude

    # Registra handlers de comando
    command_handlers = create_command_handlers(db, claude)
    for cmd_name, handler_fn in command_handlers.items():
        app.add_handler(CommandHandler(cmd_name, handler_fn))

    # Handler passivo de mensagens (captura tudo que não é comando)
    message_handler = create_message_handler(db)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Handler de callbacks (botões inline)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Agenda resumo diário
    if app.job_queue:
        async def daily_summary_callback(context):
            await summary_service.run_daily_summaries(context.bot)

        summary_time = time(hour=Config.DAILY_SUMMARY_HOUR, minute=0, second=0)
        app.job_queue.run_daily(daily_summary_callback, time=summary_time, name="daily_summary")
        logger.info(f"Resumo diário agendado para {Config.DAILY_SUMMARY_HOUR}:00 UTC")

    logger.info("Caixa Preta Bot iniciando...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
