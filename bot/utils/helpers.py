from datetime import datetime


def _format_timestamp(ts) -> str:
    """Converte timestamp (datetime ou string) para string legível."""
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M")
    return str(ts)[:16]


def _format_date(ts) -> str:
    """Converte timestamp para data curta."""
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d")
    return str(ts)[:10]


def format_messages_for_prompt(messages: list[dict]) -> str:
    """Formata lista de mensagens para enviar ao Claude."""
    lines = []
    for msg in messages:
        timestamp = _format_timestamp(msg.get("created_at"))
        name = msg.get("display_name") or msg.get("username") or "Desconhecido"
        text = msg.get("message_text", "")
        lines.append(f"[{timestamp}] {name}: {text}")
    return "\n".join(lines)


def format_decisions_for_prompt(decisions: list[dict]) -> str:
    """Formata decisões para contexto do Claude."""
    if not decisions:
        return "Nenhuma decisão registrada."
    lines = []
    for d in decisions:
        date = _format_date(d.get("created_at"))
        lines.append(f"- [{date}] {d['decision_text']}")
    return "\n".join(lines)


def format_tasks_for_prompt(tasks: list[dict]) -> str:
    """Formata pendências para contexto do Claude."""
    if not tasks:
        return "Nenhuma pendência registrada."
    lines = []
    for t in tasks:
        assigned = f" -> @{t['assigned_to']}" if t.get("assigned_to") else ""
        lines.append(f"- {t['task_text']}{assigned} ({t['status']})")
    return "\n".join(lines)


def truncate(text: str, max_length: int = 2000) -> str:
    """Trunca texto para caber no limite do Telegram."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def parse_assigned_user(text: str) -> tuple[str | None, str]:
    """Extrai usuario do início do texto. Aceita @usuario ou nome.
    Retorna (usuario, resto_do_texto).
    Se só tiver uma palavra, assume que é o texto da tarefa (sem atribuição)."""
    parts = text.strip().split(None, 1)
    if not parts:
        return None, ""
    first = parts[0]
    # Se começa com @, é claramente um usuario
    if first.startswith("@"):
        username = first[1:]
        rest = parts[1] if len(parts) > 1 else ""
        return username, rest
    # Se tem mais de uma palavra, a primeira é o responsável
    if len(parts) > 1:
        return first, parts[1]
    # Só uma palavra = texto da tarefa, sem atribuição
    return None, text.strip()
