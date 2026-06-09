from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Callable


class AuthService:
    def __init__(self, conn: sqlite3.Connection, *, one: Callable, now_iso: Callable[[], str], token_for: Callable[[int], str], public_user: Callable):
        self.conn = conn
        self.one = one
        self.now_iso = now_iso
        self.token_for = token_for
        self.public_user = public_user

    def challenge(self, hedera_account_id: str) -> dict[str, str]:
        nonce = secrets.token_hex(8)
        self.conn.execute(
            "INSERT INTO challenges (nonce, hedera_account_id, created_at) VALUES (?, ?, ?)",
            (nonce, hedera_account_id, self.now_iso()),
        )
        return {"nonce": nonce, "message": f"Sign this message to login to EscrowEye: {nonce}"}

    def login(self, body: Any) -> dict[str, Any]:
        challenge_row = self.one(
            self.conn,
            "SELECT * FROM challenges WHERE nonce = ? AND hedera_account_id = ?",
            (body.nonce, body.hedera_account_id),
        )
        _ = challenge_row, body.signature
        existing = self.conn.execute("SELECT * FROM users WHERE hedera_account_id = ?", (body.hedera_account_id,)).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE users SET hedera_public_key = COALESCE(NULLIF(?, ''), hedera_public_key), user_type = ? WHERE id = ?",
                (body.hedera_public_key, body.user_type, existing["id"]),
            )
            user = self.one(self.conn, "SELECT * FROM users WHERE id = ?", (existing["id"],))
        else:
            cur = self.conn.execute(
                """
                INSERT INTO users (email, user_type, hedera_account_id, hedera_public_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (None, body.user_type, body.hedera_account_id, body.hedera_public_key, self.now_iso()),
            )
            user = self.one(self.conn, "SELECT * FROM users WHERE id = ?", (cur.lastrowid,))
        self.conn.execute("DELETE FROM challenges WHERE nonce = ?", (body.nonce,))
        return {"token": self.token_for(user["id"]), "user": self.public_user(user)}

    def update_profile_email(self, email: str | None, user: dict[str, Any]) -> dict[str, Any]:
        self.conn.execute("UPDATE users SET email = COALESCE(?, email) WHERE id = ?", (email, user["id"]))
        row = self.one(self.conn, "SELECT id, email FROM users WHERE id = ?", (user["id"],))
        return dict(row)
