import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

    # PostgreSQL
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    # Bot Config
    ADMIN_USER_IDS_RAW = os.getenv("ADMIN_USER_IDS", "")
    DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "18"))

    @staticmethod
    def get_admin_ids() -> list[int]:
        raw = os.getenv("ADMIN_USER_IDS", "")
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
