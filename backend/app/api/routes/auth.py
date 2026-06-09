from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.auth_service import AuthService


class ChallengeIn(BaseModel):
    hedera_account_id: str


class LoginIn(BaseModel):
    hedera_account_id: str
    hedera_public_key: str = ""
    signature: str = ""
    nonce: str
    user_type: str = Field(pattern="^(owner|supplier)$")


class ProfilePatch(BaseModel):
    email: Optional[str] = None


def create_auth_router(
    *,
    db: Callable,
    now_iso: Callable[[], str],
    token_for: Callable[[int], str],
    current_user: Callable,
    public_user: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/challenge")
    async def challenge(body: ChallengeIn):
        async with db() as session:
            service = AuthService(session, now_iso=now_iso, token_for=token_for, public_user=public_user)
            return await service.challenge(body.hedera_account_id)

    @router.post("/login")
    async def login(body: LoginIn):
        async with db() as session:
            service = AuthService(session, now_iso=now_iso, token_for=token_for, public_user=public_user)
            return await service.login(body)

    @router.get("/me")
    async def me(user: dict[str, Any] = Depends(current_user)):
        return public_user(user)

    @router.patch("/profile")
    async def profile(body: ProfilePatch, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = AuthService(session, now_iso=now_iso, token_for=token_for, public_user=public_user)
            return await service.update_profile_email(body.email, user)

    return router
