from __future__ import annotations

import secrets
import sqlite3
from typing import Any, Callable

from fastapi import HTTPException

from app.core.logging import get_logger
from app.services.signature_verifier import challenge_message, signature_required, verify_wallet_signature


logger = get_logger("escroweye.auth")


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
        logger.info("auth.challenge wallet=%s", hedera_account_id)
        return {"nonce": nonce, "message": challenge_message(nonce)}

    def login(self, body: Any) -> dict[str, Any]:
        challenge_row = self.one(
            self.conn,
            "SELECT * FROM challenges WHERE nonce = ? AND hedera_account_id = ?",
            (body.nonce, body.hedera_account_id),
        )
        message = challenge_message(body.nonce)
        if signature_required():
            try:
                verified = verify_wallet_signature(body.hedera_public_key, body.signature, message)
            except ValueError:
                verified = False
            if not verified:
                logger.warning("auth.signature_failed wallet=%s", body.hedera_account_id)
                raise HTTPException(status_code=401, detail="invalid_wallet_signature")
        else:
            logger.debug("auth.signature_dev_mode wallet=%s", body.hedera_account_id)
        _ = challenge_row
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
        logger.info("auth.login user_id=%s wallet=%s role=%s", user["id"], user["hedera_account_id"], user["user_type"])
        return {"token": self.token_for(user["id"]), "user": self.public_user(user)}

    def update_profile_email(self, email: str | None, user: dict[str, Any]) -> dict[str, Any]:
        self.conn.execute("UPDATE users SET email = COALESCE(?, email) WHERE id = ?", (email, user["id"]))
        row = self.one(self.conn, "SELECT id, email FROM users WHERE id = ?", (user["id"],))
        return dict(row)
