import asyncpg
from datetime import datetime
from bot.storage.models import SCHEMA_SQL


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def initialize(self):
        self._pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            for statement in SCHEMA_SQL:
                await conn.execute(statement)

    async def close(self):
        if self._pool:
            await self._pool.close()

    # ── Groups ──

    async def get_group(self, chat_id: int) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM groups WHERE chat_id = $1", chat_id
            )
            return dict(row) if row else None

    async def get_all_active_groups(self) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM groups WHERE is_active = TRUE"
            )
            return [dict(r) for r in rows]

    async def save_group(
        self,
        chat_id: int,
        group_name: str,
        project_name: str,
        system_prompt: str,
    ):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO groups
                   (chat_id, group_name, project_name, system_prompt)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (chat_id) DO UPDATE SET
                       group_name = EXCLUDED.group_name,
                       project_name = EXCLUDED.project_name,
                       system_prompt = EXCLUDED.system_prompt""",
                chat_id, group_name, project_name, system_prompt,
            )

    # ── Messages ──

    async def save_message(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        display_name: str | None,
        message_text: str,
        telegram_message_id: int | None = None,
        reply_to: int | None = None,
        message_type: str = "text",
    ):
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO messages
                   (chat_id, user_id, username, display_name, message_text,
                    message_type, reply_to_message_id, telegram_message_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                chat_id, user_id, username, display_name,
                message_text, message_type, reply_to, telegram_message_id,
            )

    async def get_recent_messages(self, chat_id: int, limit: int = 100) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM messages
                   WHERE chat_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2""",
                chat_id, limit,
            )
            return [dict(r) for r in reversed(rows)]

    async def get_messages_since(self, chat_id: int, since: datetime) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM messages
                   WHERE chat_id = $1 AND created_at >= $2
                   ORDER BY created_at ASC""",
                chat_id, since,
            )
            return [dict(r) for r in rows]

    # ── Decisions ──

    async def save_decision(
        self,
        chat_id: int,
        user_id: int,
        decision_text: str,
        context: str | None = None,
    ) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO decisions (chat_id, user_id, decision_text, context)
                   VALUES ($1, $2, $3, $4) RETURNING id""",
                chat_id, user_id, decision_text, context,
            )
            return row["id"]

    async def get_decisions(self, chat_id: int, limit: int = 50) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM decisions
                   WHERE chat_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2""",
                chat_id, limit,
            )
            return [dict(r) for r in reversed(rows)]

    # ── Tasks ──

    async def save_task(
        self,
        chat_id: int,
        task_text: str,
        assigned_to: str | None = None,
    ) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO tasks (chat_id, assigned_to, task_text)
                   VALUES ($1, $2, $3) RETURNING id""",
                chat_id, assigned_to, task_text,
            )
            return row["id"]

    async def get_pending_tasks(self, chat_id: int) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM tasks
                   WHERE chat_id = $1 AND status IN ('pendente', 'em_andamento')
                   ORDER BY created_at ASC""",
                chat_id,
            )
            return [dict(r) for r in rows]

    async def complete_task(self, task_id: int) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE tasks
                   SET status = 'concluida', completed_at = $1
                   WHERE id = $2 AND status != 'concluida'""",
                datetime.now(), task_id,
            )
            return result == "UPDATE 1"

    async def find_task(self, chat_id: int, search: str) -> dict | None:
        async with self._pool.acquire() as conn:
            if search.isdigit():
                row = await conn.fetchrow(
                    "SELECT * FROM tasks WHERE id = $1 AND chat_id = $2",
                    int(search), chat_id,
                )
                if row:
                    return dict(row)

            row = await conn.fetchrow(
                """SELECT * FROM tasks
                   WHERE chat_id = $1 AND task_text ILIKE $2 AND status != 'concluida'
                   ORDER BY created_at DESC LIMIT 1""",
                chat_id, f"%{search}%",
            )
            return dict(row) if row else None

    # ── Stats ──

    async def get_group_stats(self, chat_id: int) -> dict:
        async with self._pool.acquire() as conn:
            stats = {}
            row = await conn.fetchrow(
                "SELECT COUNT(*) as c FROM messages WHERE chat_id = $1", chat_id
            )
            stats["total_messages"] = row["c"]

            row = await conn.fetchrow(
                "SELECT COUNT(*) as c FROM decisions WHERE chat_id = $1", chat_id
            )
            stats["total_decisions"] = row["c"]

            row = await conn.fetchrow(
                "SELECT COUNT(*) as c FROM tasks WHERE chat_id = $1 AND status != 'concluida'",
                chat_id,
            )
            stats["pending_tasks"] = row["c"]

            return stats
