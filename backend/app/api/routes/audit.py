from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends

from app.services import marketplace as marketplace_service


def create_audit_router(*, db: Callable, one: Callable, current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["audit"])

    @router.get("/service-requests/{request_id}/audit-events")
    def service_audit_events(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.audit_events(conn, request_id)

    @router.get("/service-requests/{request_id}/hcs-topic")
    def service_hcs_topic(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.hcs_topic(conn, request_id)

    @router.post("/service-requests/{request_id}/audit-events")
    def create_service_audit_event(request_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return marketplace_service.create_audit_event(conn, request_id, body)

    return router
