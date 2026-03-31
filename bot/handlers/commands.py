import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import Config
from bot.storage.database import Database
from bot.services.claude_service import ClaudeService, SYSTEM_PROMPT_TEMPLATE
from bot.utils.helpers import (
    format_messages_for_prompt,
    format_decisions_for_prompt,
    format_tasks_for_prompt,
    truncate,
    parse_assigned_user,
    _format_date,
)

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in Config.get_admin_ids()


def _quick_buttons() -> InlineKeyboardMarkup:
    """Botões de atalho para comandos frequentes."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Resumo", callback_data="cmd_resumo"),
            InlineKeyboardButton("Pendências", callback_data="cmd_pendencias"),
        ],
        [
            InlineKeyboardButton("Status", callback_data="cmd_status"),
            InlineKeyboardButton("Help", callback_data="cmd_help"),
        ],
    ])


def create_command_handlers(db: Database, claude: ClaudeService):
    """Retorna dict com todos os handlers de comando."""

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Olá! Sou o Caixa Preta, bot de memória de projetos.\n"
            "Use /setup para configurar este grupo.\n"
            "Use /help para ver todos os comandos.",
            reply_markup=_quick_buttons(),
        )

    async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        admin_ids = Config.get_admin_ids()
        is_adm = user_id in admin_ids
        await update.message.reply_text(
            f"Seu user ID: {user_id}\n"
            f"Admin IDs configurados: {admin_ids}\n"
            f"Você é admin: {is_adm}"
        )

    async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_quick_buttons())

    async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ("group", "supergroup"):
            await update.message.reply_text("Este comando só funciona em grupos.")
            return

        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Apenas administradores podem usar /setup.")
            return

        chat_id = update.effective_chat.id

        existing = await db.get_group(chat_id)
        if existing:
            await update.message.reply_text(
                f"Este grupo já está configurado como projeto *{existing['project_name']}*.",
                parse_mode="Markdown",
            )
            return

        args_text = " ".join(context.args) if context.args else ""
        project_name = args_text.strip() or update.effective_chat.title or "Projeto"

        try:
            system_prompt = SYSTEM_PROMPT_TEMPLATE.format(project_name=project_name)

            await db.save_group(
                chat_id=chat_id,
                group_name=update.effective_chat.title or project_name,
                project_name=project_name,
                system_prompt=system_prompt,
            )

            await update.message.reply_text(
                f"Projeto *{project_name}* configurado!\n"
                "Use /help para ver os comandos.",
                parse_mode="Markdown",
                reply_markup=_quick_buttons(),
            )
        except Exception as e:
            logger.error(f"Erro no /setup: {e}")
            await update.message.reply_text(f"Erro ao configurar: {e}")

    async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        messages = await db.get_recent_messages(chat_id, limit=250)
        if not messages:
            await update.message.reply_text("Sem mensagens registradas para resumir.")
            return

        await update.message.reply_text("Gerando resumo...")

        try:
            formatted = format_messages_for_prompt(messages)
            summary = await claude.generate_summary(
                project_name=group["project_name"],
                formatted_messages=formatted,
                system_prompt=group.get("system_prompt"),
            )

            await update.message.reply_text(truncate(summary, 4000), parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Erro no /resumo: {e}")
            await update.message.reply_text(f"Erro ao gerar resumo: {e}")

    async def cmd_decisao(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /decisao [texto da decisão]")
            return

        recent = await db.get_recent_messages(chat_id, limit=10)
        context_text = format_messages_for_prompt(recent) if recent else None

        username = update.effective_user.username or update.effective_user.full_name

        decision_id = await db.save_decision(
            chat_id=chat_id,
            user_id=update.effective_user.id,
            decision_text=args_text,
            context=context_text,
        )

        await update.message.reply_text(
            f"Decisão #{decision_id} registrada por @{username}: {args_text}"
        )

    async def cmd_decisoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        decisions = await db.get_decisions(chat_id, limit=20)
        if not decisions:
            await update.message.reply_text("Nenhuma decisão registrada.")
            return

        lines = [f"*Decisões do projeto {group['project_name']}:*\n"]
        for d in decisions:
            date = _format_date(d.get("created_at"))
            lines.append(f"#{d['id']} [{date}] {d['decision_text'][:80]}")

        await update.message.reply_text(
            truncate("\n".join(lines), 4000), parse_mode="Markdown"
        )

    async def cmd_excluirdecisao(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Apenas administradores podem excluir decisões.")
            return

        chat_id = update.effective_chat.id
        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip() or not args_text.strip().isdigit():
            await update.message.reply_text("Use: /excluirdecisao [número da decisão]")
            return

        decision_id = int(args_text.strip())
        deleted = await db.delete_decision(decision_id, chat_id)
        if deleted:
            await update.message.reply_text(f"Decisão #{decision_id} excluída.")
        else:
            await update.message.reply_text(f"Decisão #{decision_id} não encontrada.")

    async def cmd_pendencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /pendencia [usuario] [texto da tarefa]")
            return

        assigned_to, task_text = parse_assigned_user(args_text)
        if not task_text:
            await update.message.reply_text("Informe o texto da pendência.")
            return

        if not assigned_to:
            assigned_to = update.effective_user.username or update.effective_user.full_name

        task_id = await db.save_task(
            chat_id=chat_id,
            task_text=task_text,
            assigned_to=assigned_to,
        )

        await update.message.reply_text(
            f"Pendência #{task_id} criada para @{assigned_to}: {task_text}"
        )

    async def cmd_pendencias(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        tasks = await db.get_pending_tasks(chat_id)
        if not tasks:
            await update.message.reply_text("Nenhuma pendência aberta!")
            return

        lines = [f"*Pendências do projeto {group['project_name']}:*\n"]
        for t in tasks:
            assigned = f" -> @{t['assigned_to']}" if t.get("assigned_to") else ""
            lines.append(f"• #{t['id']} {t['task_text']}{assigned} ({t['status']})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_excluirpendencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Apenas administradores podem excluir pendências.")
            return

        chat_id = update.effective_chat.id
        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip() or not args_text.strip().isdigit():
            await update.message.reply_text("Use: /excluirpendencia [número da pendência]")
            return

        task_id = int(args_text.strip())
        deleted = await db.delete_task(task_id, chat_id)
        if deleted:
            await update.message.reply_text(f"Pendência #{task_id} excluída.")
        else:
            await update.message.reply_text(f"Pendência #{task_id} não encontrada.")

    async def cmd_feito(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /feito [número ou texto da pendência]")
            return

        task = await db.find_task(chat_id, args_text.strip())
        if not task:
            await update.message.reply_text("Pendência não encontrada.")
            return

        completed = await db.complete_task(task["id"])
        if not completed:
            await update.message.reply_text("Esta pendência já foi concluída.")
            return

        await update.message.reply_text(f"Pendência concluída: {task['task_text']}")

    async def cmd_contexto(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /contexto [sua pergunta sobre o projeto]")
            return

        await update.message.reply_text("Analisando contexto do projeto...")

        try:
            messages = await db.get_recent_messages(chat_id, limit=350)
            decisions = await db.get_decisions(chat_id)
            tasks = await db.get_pending_tasks(chat_id)

            answer = await claude.answer_context(
                project_name=group["project_name"],
                formatted_messages=format_messages_for_prompt(messages),
                formatted_decisions=format_decisions_for_prompt(decisions),
                formatted_tasks=format_tasks_for_prompt(tasks),
                user_question=args_text,
                system_prompt=group.get("system_prompt"),
            )

            await update.message.reply_text(truncate(answer, 4000), parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Erro no /contexto: {e}")
            await update.message.reply_text(f"Erro ao buscar contexto: {e}")

    async def cmd_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /buscar [sua pesquisa]")
            return

        await update.message.reply_text("Pesquisando na web...")

        try:
            result = await claude.web_search(args_text)
            await update.message.reply_text(truncate(result, 4000), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Erro no /buscar: {e}")
            await update.message.reply_text(f"Erro na pesquisa: {e}")

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Apenas administradores podem usar /status.")
            return

        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
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

        await update.message.reply_text(
            truncate("\n".join(lines), 4000), parse_mode="Markdown",
            reply_markup=_quick_buttons(),
        )

    return {
        "start": cmd_start,
        "myid": cmd_myid,
        "help": cmd_help,
        "setup": cmd_setup,
        "resumo": cmd_resumo,
        "decisao": cmd_decisao,
        "decisoes": cmd_decisoes,
        "excluirdecisao": cmd_excluirdecisao,
        "pendencia": cmd_pendencia,
        "pendencias": cmd_pendencias,
        "excluirpendencia": cmd_excluirpendencia,
        "feito": cmd_feito,
        "contexto": cmd_contexto,
        "buscar": cmd_buscar,
        "status": cmd_status,
    }
