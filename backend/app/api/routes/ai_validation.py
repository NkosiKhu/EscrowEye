from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_ai_validation_router(*, db: Callable, one: Callable, now_iso: Callable[[], str], current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ai-validation"])

    @router.post("/service-requests/{request_id}/ai-validation/run")
    def run_service_ai_validation(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.run_ai_validation(conn, request_id)

    @router.get("/service-requests/{request_id}/ai-validation")
    def get_service_ai_validation(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.get_ai_validation(conn, request_id)

    @router.post("/service-requests/{request_id}/ai-validation/request-corrections")
    def request_ai_corrections(request_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.request_ai_corrections(conn, request_id, body)

    return router
