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
    one: Callable,
    now_iso: Callable[[], str],
    token_for: Callable[[int], str],
    current_user: Callable,
    public_user: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    def service(conn) -> AuthService:
        return AuthService(conn, one=one, now_iso=now_iso, token_for=token_for, public_user=public_user)

    @router.post("/challenge")
    def challenge(body: ChallengeIn):
        with db() as conn:
            return service(conn).challenge(body.hedera_account_id)

    @router.post("/login")
    def login(body: LoginIn):
        with db() as conn:
            return service(conn).login(body)

    @router.get("/me")
    def me(user: dict[str, Any] = Depends(current_user)):
        return public_user(user)

    @router.patch("/profile")
    def profile(body: ProfilePatch, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).update_profile_email(body.email, user)

    return router
