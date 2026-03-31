import logging
from datetime import datetime, timedelta

from bot.storage.database import Database
from bot.services.claude_service import ClaudeService
from bot.utils.helpers import format_messages_for_prompt, truncate

logger = logging.getLogger(__name__)


class SummaryService:
    def __init__(self, db: Database, claude: ClaudeService):
        self.db = db
        self.claude = claude

    async def run_daily_summaries(self, bot):
        """Gera e envia resumos diários para todos os grupos ativos."""
        groups = await self.db.get_all_active_groups()
        logger.info(f"Gerando resumos diários para {len(groups)} grupos")

        for group in groups:
            try:
                await self._summarize_group(bot, group)
            except Exception as e:
                logger.error(
                    f"Erro ao gerar resumo para {group['project_name']}: {e}"
                )

    async def _summarize_group(self, bot, group: dict):
        since = datetime.now() - timedelta(hours=24)
        messages = await self.db.get_messages_since(group["chat_id"], since)

        if len(messages) < 5:
            logger.info(
                f"Poucas mensagens em {group['project_name']} ({len(messages)}), pulando resumo"
            )
            return

        formatted = format_messages_for_prompt(messages)
        summary = await self.claude.generate_summary(
            project_name=group["project_name"],
            formatted_messages=formatted,
            system_prompt=group.get("system_prompt"),
        )

        today = datetime.now().strftime("%d/%m/%Y")
        text = f"*Resumo do dia — {today}*\n\n{summary}"

        await bot.send_message(
            chat_id=group["chat_id"],
            text=truncate(text, 4000),
            parse_mode="Markdown",
        )
