from datetime import datetime


def format_messages_for_prompt(messages: list[dict]) -> str:
    """Formata lista de mensagens para enviar ao Claude."""
    lines = []
    for msg in messages:
        timestamp = msg.get("created_at", "")
        if isinstance(timestamp, str) and len(timestamp) > 16:
            timestamp = timestamp[:16]
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
        date = d.get("created_at", "")[:10] if d.get("created_at") else ""
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
    """Extrai @usuario do início do texto. Retorna (usuario, resto_do_texto)."""
    parts = text.strip().split(None, 1)
    if not parts:
        return None, ""
    if parts[0].startswith("@"):
        username = parts[0][1:]
        rest = parts[1] if len(parts) > 1 else ""
        return username, rest
    return None, text.strip()
