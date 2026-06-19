"""Platform-level config from environment (shared across all users)."""

import os

from dotenv import load_dotenv

load_dotenv()


def adzuna_credentials() -> tuple[str, str]:
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    return app_id, app_key


def deepseek_api_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "")


def telegram_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def cron_secret() -> str:
    return os.getenv("CRON_SECRET", "")


def public_base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
