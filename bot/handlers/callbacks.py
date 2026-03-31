import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import Config
from bot.storage.database import Database
from bot.services.claude_service import ClaudeService
from bot.utils.helpers import (
    format_messages_for_prompt,
    format_decisions_for_prompt,
    format_tasks_for_prompt,
    truncate,
    _format_date,
)
from bot.handlers.commands import _quick_buttons

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para callback queries de botões inline."""
    query = update.callback_query
    await query.answer()

    db: Database = context.application.bot_data["db"]
    claude: ClaudeService = context.application.bot_data["claude"]
    chat_id = update.effective_chat.id
    msg = query.message  # mensagem original que contém os botões

    if query.data == "cmd_help":
        text = (
            "*Comandos disponíveis:*\n\n"
            "/setup — Configurar grupo (admin)\n"
            "/resumo — Gerar resumo das discussões\n"
            "/decisao [texto] — Registrar uma decisão\n"
            "/decisoes — Listar decisões registradas\n"
            "/excluirdecisao [nº] — Excluir decisão (admin)\n"
            "/pendencia [usuario] [texto] — Criar pendência\n"
            "/pendencias — Listar pendências abertas\n"
            "/feito [nº ou texto] — Marcar pendência como concluída\n"
            "/excluirpendencia [nº] — Excluir pendência (admin)\n"
            "/contexto [pergunta] — Perguntar sobre o projeto\n"
            "/buscar [pesquisa] — Pesquisar na web\n"
            "/status — Status do projeto (admin)\n"
            "/help — Esta mensagem"
        )
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=_quick_buttons())
        return

    # Comandos que precisam de grupo configurado
    group = await db.get_group(chat_id)
    if not group:
        await msg.reply_text("Grupo não configurado. Use /setup primeiro.")
        return

    if query.data == "cmd_resumo":
        messages = await db.get_recent_messages(chat_id, limit=250)
        if not messages:
            await msg.reply_text("Sem mensagens registradas para resumir.")
            return

        await msg.reply_text("Gerando resumo...")
        try:
            formatted = format_messages_for_prompt(messages)
            summary = await claude.generate_summary(
                project_name=group["project_name"],
                formatted_messages=formatted,
                system_prompt=group.get("system_prompt"),
            )
            await msg.reply_text(truncate(summary, 4000), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Erro no callback resumo: {e}", exc_info=True)
            await msg.reply_text("Erro ao gerar resumo. Tente novamente.")

    elif query.data == "cmd_pendencias":
        tasks = await db.get_pending_tasks(chat_id)
        if not tasks:
            await msg.reply_text("Nenhuma pendência aberta!")
            return

        lines = [f"*Pendências do projeto {group['project_name']}:*\n"]
        for t in tasks:
            assigned = f" -> @{t['assigned_to']}" if t.get("assigned_to") else ""
            lines.append(f"• #{t['id']} {t['task_text']}{assigned} ({t['status']})")
        await msg.reply_text("\n".join(lines), parse_mode="Markdown")

    elif query.data == "cmd_status":
        user_id = update.effective_user.id
        if user_id not in Config.get_admin_ids():
            await msg.reply_text("Apenas administradores podem usar /status.")
            return

        stats = await db.get_group_stats(chat_id)
        decisions = await db.get_decisions(chat_id, limit=10)
        tasks = await db.get_pending_tasks(chat_id)

        lines = [
            f"*Status do projeto {group['project_name']}*\n",
            f"Mensagens registradas: {stats['total_messages']}",
            f"Configurado em: {_format_date(group.get('created_at'))}\n",
        ]

        lines.append(f"*Decisões ({stats['total_decisions']} total):*")
        if decisions:
            for d in decisions[-5:]:
                date = _format_date(d.get("created_at"))
                lines.append(f"• #{d['id']} [{date}] {d['decision_text'][:80]}")
        else:
            lines.append("• Nenhuma decisão registrada")

        lines.append(f"\n*Pendências abertas ({stats['pending_tasks']}):*")
        if tasks:
            for t in tasks:
                assigned = f" -> @{t['assigned_to']}" if t.get("assigned_to") else ""
                lines.append(f"• #{t['id']} {t['task_text'][:60]}{assigned}")
        else:
            lines.append("• Nenhuma pendência aberta")

        await msg.reply_text(
            truncate("\n".join(lines), 4000), parse_mode="Markdown",
            reply_markup=_quick_buttons(),
        )

    else:
        logger.warning(f"Callback desconhecido: {query.data}")
