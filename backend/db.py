"""
Lightweight SQLite persistence layer for the Telecom Workflow Navigator.

Currently used for: user feedback (thumbs up/down + optional comment).
Kept deliberately small — stdlib sqlite3 only, no ORM — since this is a
single-process FastAPI app. If concurrent write volume ever becomes an
issue, swap this module for a proper DB without touching main.py's
call sites (init_db / insert_feedback / fetch_feedback).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "app_data.db"
LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Creates tables if they don't exist, and migrates older DBs that
    predate the question/answer columns. Safe to call on every startup."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'default',
                message_id TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('up', 'down', 'comment')),
                comment TEXT,
                question TEXT,
                answer TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_session_id ON feedback(session_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON feedback(message_id)"
        )

        # Migration: if this is an existing DB created before question/answer
        # existed, add the columns instead of failing.
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(feedback)")}
        if "question" not in existing_columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN question TEXT")
        if "answer" not in existing_columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN answer TEXT")


def insert_feedback(
    session_id: str,
    message_id: str,
    type_: str,
    comment: str | None,
    question: str | None = None,
    answer: str | None = None,
) -> int:
    """Inserts one feedback row and returns its new id. created_at is stamped
    explicitly in IST (Asia/Kolkata) rather than relying on SQLite's
    datetime('now'), which returns UTC and would show times ~5.5 hours behind."""
    created_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback (session_id, message_id, type, comment, question, answer, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, message_id, type_, comment, question, answer, created_at),
        )
        return cursor.lastrowid


def fetch_feedback(session_id: str | None = None, limit: int = 100) -> list[dict]:
    """
    Returns recent feedback rows, newest first. Pass session_id to filter
    to one conversation; omit it to see everything (e.g. for a demo/admin view).
    """
    with get_connection() as conn:
        if session_id:
            rows = conn.execute(
                """
                SELECT id, session_id, message_id, type, comment, question, answer, created_at
                FROM feedback
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, session_id, message_id, type, comment, question, answer, created_at
                FROM feedback
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def feedback_counts() -> dict:
    """Aggregate counts by type — handy for a quick dashboard stat."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT type, COUNT(*) as count FROM feedback GROUP BY type"
        ).fetchall()
        return {row["type"]: row["count"] for row in rows}