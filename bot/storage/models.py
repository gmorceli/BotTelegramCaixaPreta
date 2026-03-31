SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS groups (
        chat_id BIGINT PRIMARY KEY,
        group_name TEXT NOT NULL,
        project_name TEXT NOT NULL,
        notion_database_id TEXT,
        system_prompt TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        username TEXT,
        display_name TEXT,
        message_text TEXT NOT NULL,
        message_type TEXT DEFAULT 'text',
        reply_to_message_id BIGINT,
        telegram_message_id BIGINT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        decision_text TEXT NOT NULL,
        context TEXT,
        notion_page_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        assigned_to TEXT,
        task_text TEXT NOT NULL,
        status TEXT DEFAULT 'pendente',
        notion_page_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_chat_id_status ON tasks(chat_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_chat_id ON decisions(chat_id)",
]
