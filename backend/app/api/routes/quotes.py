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


def create_quotes_router(*, db: Callable, one: Callable, now_iso: Callable[[], str], current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["quotes"])

    @router.post("/service-requests/{request_id}/quotes", status_code=201)
    def create_request_quote(request_id: int, body: QuoteIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.create_quote(conn, request_id, body, user)

    @router.get("/service-requests/{request_id}/quotes")
    def list_request_quotes(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.list_request_quotes(conn, request_id)

    @router.post("/quotes/{quote_id}/accept")
    def accept_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.accept_quote(conn, quote_id, user)

    @router.post("/quotes/{quote_id}/reject")
    def reject_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.reject_quote(conn, quote_id, user)

    @router.post("/quotes/{quote_id}/withdraw")
    def withdraw_request_quote(quote_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return marketplace_service.withdraw_quote(conn, quote_id, user)

    return router
