import os
import aiosqlite
from datetime import datetime
from bot.storage.models import SCHEMA_SQL


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    # ── Groups ──

    async def get_group(self, chat_id: int) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM groups WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_active_groups(self) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM groups WHERE is_active = 1"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def save_group(
        self,
        chat_id: int,
        group_name: str,
        project_name: str,
        notion_database_id: str,
        system_prompt: str,
    ):
        await self._db.execute(
            """INSERT OR REPLACE INTO groups
               (chat_id, group_name, project_name, notion_database_id, system_prompt)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, group_name, project_name, notion_database_id, system_prompt),
        )
        await self._db.commit()

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
        await self._db.execute(
            """INSERT INTO messages
               (chat_id, user_id, username, display_name, message_text,
                message_type, reply_to_message_id, telegram_message_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_id, user_id, username, display_name,
                message_text, message_type, reply_to, telegram_message_id,
            ),
        )
        await self._db.commit()

    async def get_recent_messages(self, chat_id: int, limit: int = 100) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM messages
               WHERE chat_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (chat_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]

    async def get_messages_since(self, chat_id: int, since: datetime) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM messages
               WHERE chat_id = ? AND created_at >= ?
               ORDER BY created_at ASC""",
            (chat_id, since.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Decisions ──

    async def save_decision(
        self,
        chat_id: int,
        user_id: int,
        decision_text: str,
        context: str | None = None,
        notion_page_id: str | None = None,
    ) -> int:
        cursor = await self._db.execute(
            """INSERT INTO decisions (chat_id, user_id, decision_text, context, notion_page_id)
               VALUES (?, ?, ?, ?, ?)""",
            (chat_id, user_id, decision_text, context, notion_page_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_decisions(self, chat_id: int, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM decisions
               WHERE chat_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (chat_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in reversed(rows)]

    # ── Tasks ──

    async def save_task(
        self,
        chat_id: int,
        task_text: str,
        assigned_to: str | None = None,
        notion_page_id: str | None = None,
    ) -> int:
        cursor = await self._db.execute(
            """INSERT INTO tasks (chat_id, assigned_to, task_text, notion_page_id)
               VALUES (?, ?, ?, ?)""",
            (chat_id, assigned_to, task_text, notion_page_id),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_pending_tasks(self, chat_id: int) -> list[dict]:
        async with self._db.execute(
            """SELECT * FROM tasks
               WHERE chat_id = ? AND status IN ('pendente', 'em_andamento')
               ORDER BY created_at ASC""",
            (chat_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def complete_task(self, task_id: int) -> bool:
        cursor = await self._db.execute(
            """UPDATE tasks
               SET status = 'concluida', completed_at = ?
               WHERE id = ? AND status != 'concluida'""",
            (datetime.now().isoformat(), task_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def find_task(self, chat_id: int, search: str) -> dict | None:
        # Try by ID first
        if search.isdigit():
            async with self._db.execute(
                "SELECT * FROM tasks WHERE id = ? AND chat_id = ?",
                (int(search), chat_id),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)

        # Search by text
        async with self._db.execute(
            """SELECT * FROM tasks
               WHERE chat_id = ? AND task_text LIKE ? AND status != 'concluida'
               ORDER BY created_at DESC LIMIT 1""",
            (chat_id, f"%{search}%"),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    # ── Stats ──

    async def get_group_stats(self, chat_id: int) -> dict:
        stats = {}
        async with self._db.execute(
            "SELECT COUNT(*) as c FROM messages WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            stats["total_messages"] = (await cursor.fetchone())["c"]

        async with self._db.execute(
            "SELECT COUNT(*) as c FROM decisions WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            stats["total_decisions"] = (await cursor.fetchone())["c"]

        async with self._db.execute(
            "SELECT COUNT(*) as c FROM tasks WHERE chat_id = ? AND status != 'concluida'",
            (chat_id,),
        ) as cursor:
            stats["pending_tasks"] = (await cursor.fetchone())["c"]

        return stats
