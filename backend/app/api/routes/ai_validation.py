from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_ai_validation_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ai-validation"])

    @router.post("/service-requests/{request_id}/ai-validation/run")
    async def run_service_ai_validation(request_id: int, _user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.run_ai_validation(session, request_id)

    @router.get("/service-requests/{request_id}/ai-validation")
    async def get_service_ai_validation(request_id: int, _user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.get_ai_validation(session, request_id)

    @router.post("/service-requests/{request_id}/ai-validation/request-corrections")
    async def request_ai_corrections(request_id: int, body: dict[str, Any], _user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.request_ai_corrections(session, request_id, body)

    return router
