from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services import marketplace as marketplace_service


class QuoteIn(BaseModel):
    amount: int
    message: Optional[str] = None
    scope: Optional[str] = None
    timeline: Optional[str] = None


def create_quotes_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["quotes"])

    @router.post("/service-requests/{request_id}/quotes", status_code=201)
    async def create_request_quote(request_id: int, body: QuoteIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.create_quote(session, request_id, body, user)

    @router.get("/service-requests/{request_id}/quotes")
    async def list_request_quotes(request_id: int, _user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.list_request_quotes(session, request_id)

    @router.post("/quotes/{quote_id}/accept")
    async def accept_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.accept_quote(session, quote_id, user)

    @router.post("/quotes/{quote_id}/reject")
    async def reject_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.reject_quote(session, quote_id, user)

    @router.post("/quotes/{quote_id}/withdraw")
    async def withdraw_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.withdraw_quote(session, quote_id, user)

    return router
