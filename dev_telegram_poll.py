"""
Local dev helper: poll Telegram for /start messages when webhook is not set up.
Run in a second terminal while testing the web app locally:

  python dev_telegram_poll.py
"""

import time

import requests
from dotenv import load_dotenv

from app import config, database
from app.main import get_bot_username

load_dotenv()
database.init_db()

OFFSET = 0


def process_update(update: dict) -> None:
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id or not text.startswith("/start"):
        return

    parts = text.split(maxsplit=1)
    user_id = parts[1].strip() if len(parts) > 1 else None
    token = config.telegram_bot_token()

    if user_id and database.link_telegram(user_id, str(chat_id)):
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": (
                    "You're connected! You'll receive a daily UK job digest each morning."
                ),
            },
            timeout=10,
        )
        print(f"Linked user {user_id} → chat {chat_id}")
    elif user_id:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "Invalid sign-up link. Please sign up on the website again."},
            timeout=10,
        )


def main():
    token = config.telegram_bot_token()
    if not token:
        print("Set TELEGRAM_BOT_TOKEN in .env")
        return

    print(f"Polling Telegram as @{get_bot_username()} — press Ctrl+C to stop")
    global OFFSET

    while True:
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": OFFSET, "timeout": 30},
            timeout=35,
        )
        if not response.ok:
            print(f"Poll error: {response.status_code}")
            time.sleep(5)
            continue

        for update in response.json().get("result", []):
            OFFSET = update["update_id"] + 1
            process_update(update)

        time.sleep(1)


if __name__ == "__main__":
    main()
