from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_earnings_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["earnings"])

    @router.get("/supplier/earnings")
    async def supplier_earnings(user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.supplier_earnings(session, user)

    @router.get("/supplier/transactions")
    async def supplier_transactions(user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.supplier_transactions(session, user)

    @router.get("/owner/payments")
    async def owner_payments(user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.owner_payments(session, user)

    @router.get("/owner/transactions")
    async def owner_transactions(user: dict[str, Any] = Depends(current_user)):
        return await owner_payments(user)

    return router
