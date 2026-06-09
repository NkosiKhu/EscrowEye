from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from app.services._base import add_audit, audit_events, get_job
from app.services.marketplace import hcs_topic


def create_audit_router(*, db: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["audit"])

    @router.get("/service-requests/{request_id}/audit-events")
    async def service_audit_events(request_id: int, _user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await audit_events(session, request_id)

    @router.get("/service-requests/{request_id}/hcs-topic")
    async def service_hcs_topic(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await hcs_topic(session, request_id)

    @router.post("/service-requests/{request_id}/audit-events")
    async def create_service_audit_event(request_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            await get_job(session, request_id)
            await add_audit(session, request_id, str(body.get("event_type", "custom_event")), body)
            return {"request_id": request_id, "status": "recorded"}

    return router
