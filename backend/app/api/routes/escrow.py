from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services import marketplace as marketplace_service


class DisputeCreateIn(BaseModel):
    reason: str = "Owner opened a dispute."


def create_escrow_router(*, db: Callable, now_iso: Callable[[], str], current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["escrow"])

    @router.post("/service-requests/{request_id}/base-fee")
    async def pay_base_fee(request_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.pay_base_fee(session, request_id, user)

    @router.post("/service-requests/{request_id}/fund-escrow")
    async def fund_service_escrow(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        async with db() as session:
            return await marketplace_service.fund_escrow(session, request_id, user)

    @router.get("/service-requests/{request_id}/escrow")
    async def service_escrow(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.service_escrow(session, request_id)

    @router.post("/service-requests/{request_id}/confirm-satisfaction")
    async def confirm_service_satisfaction(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        async with db() as session:
            return await marketplace_service.confirm_satisfaction(session, request_id, user)

    @router.post("/service-requests/{request_id}/release-payment")
    async def release_service_payment(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        async with db() as session:
            return await marketplace_service.release_payment(session, request_id, user)

    @router.post("/service-requests/{request_id}/dispute")
    async def dispute_service_request(request_id: int, body: DisputeCreateIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.dispute_service_request(session, request_id, body.reason, user)

    return router
