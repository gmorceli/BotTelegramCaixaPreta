import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    # Notion
    NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
    NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "")

    # Bot Config
    ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "")
    DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "18"))
    MESSAGE_BUFFER_LIMIT = int(os.getenv("MESSAGE_BUFFER_LIMIT", "500"))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    @staticmethod
    def get_admin_ids() -> list[int]:
        raw = os.getenv("ADMIN_USER_IDS", "")
        ids = [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
        return ids
