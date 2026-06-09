from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings

DB_PATH: Path = settings.DATABASE_PATH
UPLOAD_DIR: Path = settings.UPLOAD_DIR


@contextmanager
def db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"No row found for: {sql[:60]}")
    return dict(row)


def insert_message(conn: sqlite3.Connection, job_id: int, sender_user_id: int | None, sender_type: str, body: str, photo_ids: list[int]) -> dict[str, Any]:
    cur = conn.execute(
        "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, sender_user_id, sender_type, body, now_iso()),
    )
    msg_id = cur.lastrowid
    for pid in photo_ids:
        conn.execute("INSERT INTO message_photos (message_id, photo_id) VALUES (?, ?)", (msg_id, pid))
    conn.commit()
    return dict(conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone())


def add_audit(conn: sqlite3.Connection, job_id: int, event_type: str, tx_hash: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_events (job_id, event_type, consensus_timestamp, metadata) VALUES (?, ?, ?, ?)",
        (job_id, event_type, now_iso(), tx_hash or ""),
    )
