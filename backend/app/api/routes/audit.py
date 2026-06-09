from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_audit_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["audit"])

    @router.get("/service-requests/{request_id}/audit-events")
    async def service_audit_events(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.audit_events(session, request_id)

    @router.get("/service-requests/{request_id}/hcs-topic")
    async def service_hcs_topic(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.hcs_topic(session, request_id)

    @router.post("/service-requests/{request_id}/audit-events")
    async def create_service_audit_event(request_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.create_audit_event(session, request_id, body)

    return router
