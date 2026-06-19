"""SQLite storage for multi-user web app."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from user_profile import UserProfile

DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "app/data.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(db_path: str = DEFAULT_DB_PATH):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY REFERENCES users(id),
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS telegram_links (
                user_id TEXT PRIMARY KEY REFERENCES users(id),
                chat_id TEXT NOT NULL,
                linked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seen_jobs (
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                seen_at TEXT NOT NULL,
                PRIMARY KEY (user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS digest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                job_count INTEGER NOT NULL,
                mode TEXT NOT NULL
            );
            """
        )


def update_user_profile(user_id: str, profile: UserProfile, db_path: str = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE profiles SET data = ? WHERE user_id = ?",
            (json.dumps(profile.to_dict()), user_id),
        )


def create_user(email: str, profile: UserProfile, db_path: str = DEFAULT_DB_PATH) -> str:
    user_id = str(uuid.uuid4())
    profile.email = email
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)",
            (user_id, email.lower().strip(), _utc_now()),
        )
        conn.execute(
            "INSERT INTO profiles (user_id, data) VALUES (?, ?)",
            (user_id, json.dumps(profile.to_dict())),
        )
    return user_id


def get_user_profile(user_id: str, db_path: str = DEFAULT_DB_PATH) -> UserProfile | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT p.data FROM profiles p JOIN users u ON u.id = p.user_id WHERE u.id = ? AND u.active = 1",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return UserProfile.from_dict(json.loads(row["data"]))


def get_user_by_email(email: str, db_path: str = DEFAULT_DB_PATH) -> str | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ? AND active = 1",
            (email.lower().strip(),),
        ).fetchone()
    return row["id"] if row else None


def link_telegram(user_id: str, chat_id: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        exists = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not exists:
            return False
        conn.execute(
            """
            INSERT INTO telegram_links (user_id, chat_id, linked_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET chat_id = excluded.chat_id, linked_at = excluded.linked_at
            """,
            (user_id, str(chat_id), _utc_now()),
        )
    return True


def get_telegram_chat_id(user_id: str, db_path: str = DEFAULT_DB_PATH) -> str | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT chat_id FROM telegram_links WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["chat_id"] if row else None


def user_status(user_id: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    with get_connection(db_path) as conn:
        user = conn.execute(
            "SELECT email, created_at FROM users WHERE id = ? AND active = 1",
            (user_id,),
        ).fetchone()
        if not user:
            return {"found": False}
        telegram = conn.execute(
            "SELECT chat_id, linked_at FROM telegram_links WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return {
        "found": True,
        "email": user["email"],
        "created_at": user["created_at"],
        "telegram_linked": telegram is not None,
        "telegram_linked_at": telegram["linked_at"] if telegram else None,
    }


def load_seen_ids(user_id: str, db_path: str = DEFAULT_DB_PATH) -> set[str]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT job_id FROM seen_jobs WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {row["job_id"] for row in rows}


def record_job_ids(user_id: str, jobs: list, db_path: str = DEFAULT_DB_PATH) -> int:
    now = _utc_now()
    with get_connection(db_path) as conn:
        for job in jobs:
            job_id = job.get("id")
            if job_id is None:
                continue
            conn.execute(
                """
                INSERT INTO seen_jobs (user_id, job_id, seen_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id, job_id) DO NOTHING
                """,
                (user_id, str(job_id), now),
            )
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM seen_jobs WHERE user_id = ?",
            (user_id,),
        ).fetchone()["c"]
    return count


def log_digest(user_id: str, job_count: int, mode: str, db_path: str = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO digest_log (user_id, sent_at, job_count, mode) VALUES (?, ?, ?, ?)",
            (user_id, _utc_now(), job_count, mode),
        )


def list_active_users_with_telegram(db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.email, t.chat_id
            FROM users u
            JOIN telegram_links t ON t.user_id = u.id
            WHERE u.active = 1
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_digest_history(user_id: str, limit: int = 7, db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT sent_at, job_count, mode
            FROM digest_log
            WHERE user_id = ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def profile_to_api(user_id: str, db_path: str = DEFAULT_DB_PATH) -> dict | None:
    profile = get_user_profile(user_id, db_path)
    if not profile:
        return None
    data = profile.to_dict()
    data["skills"] = ", ".join(profile.skills)
    data["target_titles"] = ", ".join(profile.target_titles)
    data["track_a_queries"] = ", ".join(profile.track_a_queries)
    data["track_b_queries"] = ", ".join(profile.track_b_queries)
    return data
