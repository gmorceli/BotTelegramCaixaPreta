import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import Config
from bot.storage.database import Database
from bot.services.claude_service import ClaudeService, SYSTEM_PROMPT_TEMPLATE
from bot.services.notion_service import NotionService
from bot.utils.helpers import (
    format_messages_for_prompt,
    format_decisions_for_prompt,
    format_tasks_for_prompt,
    truncate,
    parse_assigned_user,
)

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    admin_ids = Config.get_admin_ids()
    logger.info(f"Checking admin: user_id={user_id}, admin_ids={admin_ids}")
    return user_id in admin_ids


def create_command_handlers(db: Database, claude: ClaudeService, notion: NotionService):
    """Retorna dict com todos os handlers de comando."""

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Olá! Sou o Caixa Preta, bot de memória de projetos.\n"
            "Use /setup para configurar este grupo.\n"
            "Use /help para ver todos os comandos."
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
            "/pendencia [@user] [texto] — Criar pendência\n"
            "/pendencias — Listar pendências abertas\n"
            "/feito [nº ou texto] — Marcar pendência como concluída\n"
            "/contexto [pergunta] — Perguntar sobre o projeto\n"
            "/status — Status do projeto (admin)\n"
            "/help — Esta mensagem"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ("group", "supergroup"):
            await update.message.reply_text("Este comando só funciona em grupos.")
            return

        if not is_admin(update.effective_user.id):
            await update.message.reply_text("Apenas administradores podem usar /setup.")
            return

        chat_id = update.effective_chat.id

        # Verifica se já está configurado
        existing = await db.get_group(chat_id)
        if existing:
            await update.message.reply_text(
                f"Este grupo já está configurado como projeto *{existing['project_name']}*.",
                parse_mode="Markdown",
            )
            return

        # Usa o argumento como nome do projeto, ou o nome do grupo
        args_text = " ".join(context.args) if context.args else ""
        project_name = args_text.strip() or update.effective_chat.title or "Projeto"

        await update.message.reply_text(f"Configurando projeto *{project_name}*...", parse_mode="Markdown")

        try:
            # Cria database no Notion
            notion_db_id = notion.create_project_database(project_name)

            # System prompt padrão
            system_prompt = SYSTEM_PROMPT_TEMPLATE.format(project_name=project_name)

            # Salva no SQLite
            await db.save_group(
                chat_id=chat_id,
                group_name=update.effective_chat.title or project_name,
                project_name=project_name,
                notion_database_id=notion_db_id,
                system_prompt=system_prompt,
            )

            await update.message.reply_text(
                f"Projeto *{project_name}* configurado!\n"
                "Database Notion criada. Use /help para ver os comandos.",
                parse_mode="Markdown",
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

        messages = await db.get_recent_messages(chat_id, limit=100)
        if not messages:
            await update.message.reply_text("Sem mensagens registradas para resumir.")
            return

        await update.message.reply_text("Gerando resumo...")

        try:
            formatted = format_messages_for_prompt(messages)
            summary = claude.generate_summary(
                project_name=group["project_name"],
                formatted_messages=formatted,
                system_prompt=group.get("system_prompt"),
            )

            await update.message.reply_text(truncate(summary, 4000), parse_mode="Markdown")

            # Salva no Notion
            try:
                notion.create_page(
                    database_id=group["notion_database_id"],
                    tipo="resumo",
                    titulo=f"Resumo — {group['project_name']}",
                    conteudo=summary,
                    autor="Caixa Preta",
                    grupo_telegram=group["group_name"],
                )
            except Exception as e:
                logger.error(f"Erro ao salvar resumo no Notion: {e}")

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

        # Busca 10 mensagens anteriores como contexto
        recent = await db.get_recent_messages(chat_id, limit=10)
        context_text = format_messages_for_prompt(recent) if recent else None

        username = update.effective_user.username or update.effective_user.full_name

        # Salva no Notion
        notion_page_id = None
        try:
            notion_page_id = notion.create_page(
                database_id=group["notion_database_id"],
                tipo="decisão",
                titulo=args_text[:100],
                conteudo=args_text,
                autor=username,
                contexto=context_text,
                grupo_telegram=group["group_name"],
            )
        except Exception as e:
            logger.error(f"Erro ao salvar decisão no Notion: {e}")

        # Salva no SQLite
        await db.save_decision(
            chat_id=chat_id,
            user_id=update.effective_user.id,
            decision_text=args_text,
            context=context_text,
            notion_page_id=notion_page_id,
        )

        await update.message.reply_text(
            f"Decisão registrada por @{username}: {args_text}"
        )

    async def cmd_pendencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        group = await db.get_group(chat_id)
        if not group:
            await update.message.reply_text("Grupo não configurado. Use /setup primeiro.")
            return

        args_text = " ".join(context.args) if context.args else ""
        if not args_text.strip():
            await update.message.reply_text("Use: /pendencia [@usuario] [texto da tarefa]")
            return

        assigned_to, task_text = parse_assigned_user(args_text)
        if not task_text:
            await update.message.reply_text("Informe o texto da pendência.")
            return

        # Se não atribuiu a ninguém, atribui a quem enviou
        if not assigned_to:
            assigned_to = update.effective_user.username or update.effective_user.full_name

        # Salva no Notion
        notion_page_id = None
        try:
            notion_page_id = notion.create_page(
                database_id=group["notion_database_id"],
                tipo="pendência",
                titulo=task_text[:100],
                conteudo=task_text,
                autor=update.effective_user.username or update.effective_user.full_name,
                responsavel=assigned_to,
                status="pendente",
                grupo_telegram=group["group_name"],
            )
        except Exception as e:
            logger.error(f"Erro ao salvar pendência no Notion: {e}")

        # Salva no SQLite
        task_id = await db.save_task(
            chat_id=chat_id,
            task_text=task_text,
            assigned_to=assigned_to,
            notion_page_id=notion_page_id,
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

        # Atualiza no Notion
        if task.get("notion_page_id"):
            try:
                notion.update_page_status(task["notion_page_id"], "concluída")
            except Exception as e:
                logger.error(f"Erro ao atualizar Notion: {e}")

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
            messages = await db.get_recent_messages(chat_id, limit=200)
            decisions = await db.get_decisions(chat_id)
            tasks = await db.get_pending_tasks(chat_id)

            answer = claude.answer_context(
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

        text = (
            f"*Status do projeto {group['project_name']}*\n\n"
            f"Mensagens registradas: {stats['total_messages']}\n"
            f"Decisões: {stats['total_decisions']}\n"
            f"Pendências abertas: {stats['pending_tasks']}\n"
            f"Configurado em: {group['created_at']}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    return {
        "start": cmd_start,
        "myid": cmd_myid,
        "help": cmd_help,
        "setup": cmd_setup,
        "resumo": cmd_resumo,
        "decisao": cmd_decisao,
        "pendencia": cmd_pendencia,
        "pendencias": cmd_pendencias,
        "feito": cmd_feito,
        "contexto": cmd_contexto,
        "status": cmd_status,
    }
