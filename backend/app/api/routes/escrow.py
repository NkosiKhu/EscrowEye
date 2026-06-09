from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services import marketplace as marketplace_service


class DisputeCreateIn(BaseModel):
    reason: str = "Owner opened a dispute."


def create_escrow_router(*, db: Callable, one: Callable, now_iso: Callable[[], str], current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["escrow"])

    @router.post("/service-requests/{request_id}/base-fee")
    def pay_base_fee(request_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.pay_base_fee(conn, request_id, user)

    @router.post("/service-requests/{request_id}/fund-escrow")
    def fund_service_escrow(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        with db() as conn:
            return marketplace_service.fund_escrow(conn, request_id, user)

    @router.get("/service-requests/{request_id}/escrow")
    def service_escrow(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.service_escrow(conn, request_id)

    @router.post("/service-requests/{request_id}/confirm-satisfaction")
    def confirm_service_satisfaction(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        with db() as conn:
            return marketplace_service.confirm_satisfaction(conn, request_id, user)

    @router.post("/service-requests/{request_id}/release-payment")
    def release_service_payment(request_id: int, body: dict[str, Any] | None = None, user: dict[str, Any] = Depends(current_user)):
        _ = body
        with db() as conn:
            return marketplace_service.release_payment(conn, request_id, user)

    @router.post("/service-requests/{request_id}/dispute")
    def dispute_service_request(request_id: int, body: DisputeCreateIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.dispute_service_request(conn, request_id, body.reason, user)

    return router
