from __future__ import annotations

import secrets
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.models import Challenge, User
from app.services.signature_verifier import challenge_message, signature_required, verify_wallet_signature


logger = get_logger("escroweye.auth")


class AuthService:
    def __init__(self, session: AsyncSession, *, now_iso: Callable[[], str], token_for: Callable[[int], str], public_user: Callable):
        self.session = session
        self.now_iso = now_iso
        self.token_for = token_for
        self.public_user = public_user

    async def challenge(self, hedera_account_id: str) -> dict[str, str]:
        nonce = secrets.token_hex(8)
        challenge = Challenge(
            nonce=nonce,
            hedera_account_id=hedera_account_id,
            created_at=self.now_iso(),
        )
        self.session.add(challenge)
        await self.session.flush()
        logger.info("auth.challenge wallet=%s", hedera_account_id)
        return {"nonce": nonce, "message": challenge_message(nonce)}

    async def login(self, body: Any) -> dict[str, Any]:
        result = await self.session.execute(
            select(Challenge).where(
                Challenge.nonce == body.nonce,
                Challenge.hedera_account_id == body.hedera_account_id,
            )
        )
        challenge_row = result.scalar_one_or_none()
        if challenge_row is None:
            raise HTTPException(status_code=401, detail="invalid_challenge")

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

        result = await self.session.execute(
            select(User).where(User.hedera_account_id == body.hedera_account_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            if body.hedera_public_key:
                existing.hedera_public_key = body.hedera_public_key
            existing.user_type = body.user_type
            user = existing
        else:
            user = User(
                email=None,
                user_type=body.user_type,
                hedera_account_id=body.hedera_account_id,
                hedera_public_key=body.hedera_public_key,
                created_at=self.now_iso(),
            )
            self.session.add(user)
            await self.session.flush()

        await self.session.delete(challenge_row)

        logger.info("auth.login user_id=%s wallet=%s role=%s", user.id, user.hedera_account_id, user.user_type)
        return {
            "token": self.token_for(user.id),
            "user": self.public_user({
                "id": user.id,
                "email": user.email,
                "user_type": user.user_type,
                "hedera_account_id": user.hedera_account_id,
                "hedera_public_key": user.hedera_public_key,
            }),
        }

    async def update_profile_email(self, email: str | None, user: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.execute(
            select(User).where(User.id == user["id"])
        )
        db_user = result.scalar_one_or_none()
        if db_user is None:
            raise HTTPException(status_code=404, detail="not_found")
        if email is not None:
            db_user.email = email
        await self.session.flush()
        return {"id": db_user.id, "email": db_user.email}
