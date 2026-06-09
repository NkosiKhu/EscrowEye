from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_earnings_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["earnings"])

    @router.get("/supplier/earnings")
    def supplier_earnings(user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.supplier_earnings(conn, user)

    @router.get("/supplier/transactions")
    def supplier_transactions(user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.supplier_transactions(conn, user)

    @router.get("/owner/payments")
    def owner_payments(user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.owner_payments(conn, user)

    @router.get("/owner/transactions")
    def owner_transactions(user: dict[str, Any] = Depends(current_user)):
        return owner_payments(user)

    return router
