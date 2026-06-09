from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.infrastructure.x402_service import X402ConfigurationError
from app.services import marketplace as marketplace_service
from app.services.demo_seed import seed_demo_data


class ProfileSetupIn(BaseModel):
    first_name: str = ""
    last_name: str = ""
    location: str = ""
    service_area: str = ""
    profile_photo_url: str = ""
    payment_token_preference: str = "HBAR"


class ServiceRequestIn(BaseModel):
    title: str
    description: str
    address: str
    location_description: Optional[str] = None
    schedule: Optional[str] = None
    budget_amount: int
    category: Optional[str] = None


class MessageCreateIn(BaseModel):
    body: str
    type: str = "text"


def create_service_requests_router(
    *,
    db: Callable,
    now_iso: Callable[[], str],
    current_user: Callable,
    public_user: Callable,
    x402_service: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["service-requests"])

    @router.post("/onboarding/role")
    async def onboarding_role(body: dict[str, str], user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.set_user_role(session, user, body.get("role", ""))

    @router.post("/profile/setup")
    @router.patch("/profile")
    async def setup_profile(body: ProfileSetupIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.setup_profile(session, body, user, public_user)

    @router.post("/service-requests", status_code=201)
    async def create_service_request(
        body: ServiceRequestIn,
        request: Request,
        x_payment: str | None = Header(default=None),
        x_402_payment: str | None = Header(default=None),
        user: dict[str, Any] = Depends(current_user),
    ):
        _ = x_payment, x_402_payment
        try:
            payment = x402_service.authorize_headers(dict(request.headers))
        except X402ConfigurationError as error:
            return JSONResponse(
                status_code=402,
                content={"error": "payment_verification_required", "detail": str(error), "payment_requirements": x402_service.payment_requirements()},
            )
        if not payment.get("valid"):
            return JSONResponse(status_code=402, content={"error": "payment_required", "payment_requirements": x402_service.payment_requirements()})
        async with db() as session:
            return await marketplace_service.create_request(session, body, user)

    @router.get("/service-requests")
    async def list_service_requests(user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.list_service_requests(session, user)

    @router.get("/service-requests/{request_id}")
    async def get_service_request(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.get_service_request(session, request_id)

    @router.patch("/service-requests/{request_id}")
    async def update_service_request(request_id: int, body: ServiceRequestIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.update_service_request(session, request_id, body, user)

    @router.post("/service-requests/{request_id}/cancel")
    async def cancel_service_request(request_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.cancel_service_request(session, request_id, user)

    @router.get("/supplier/jobs/offers")
    async def supplier_job_offers(user: dict[str, Any] = Depends(current_user)):
        marketplace_service.require_role(user, "supplier")
        async with db() as session:
            return {"jobs": await marketplace_service.supplier_jobs(session, user, "offers")}

    @router.get("/supplier/jobs/active")
    async def supplier_job_active(user: dict[str, Any] = Depends(current_user)):
        marketplace_service.require_role(user, "supplier")
        async with db() as session:
            return {"jobs": await marketplace_service.supplier_jobs(session, user, "active")}

    @router.get("/supplier/jobs/archived")
    async def supplier_job_archived(user: dict[str, Any] = Depends(current_user)):
        marketplace_service.require_role(user, "supplier")
        async with db() as session:
            return {"jobs": await marketplace_service.supplier_jobs(session, user, "archived")}

    @router.post("/supplier/jobs/{job_id}/accept")
    async def supplier_accept_job(job_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.supplier_accept_job(session, job_id, user)

    @router.post("/supplier/jobs/{job_id}/mark-processing")
    async def supplier_mark_processing(job_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.supplier_mark_processing(session, job_id, user)

    @router.post("/supplier/jobs/{job_id}/mark-complete")
    async def supplier_mark_complete(job_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.supplier_mark_complete(session, job_id, user)

    @router.get("/service-requests/{request_id}/messages")
    async def list_service_messages(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await marketplace_service.list_service_messages(session, request_id)

    @router.post("/service-requests/{request_id}/messages")
    async def create_service_message(request_id: int, body: MessageCreateIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            return await marketplace_service.create_service_message(session, request_id, body, user)

    @router.post("/demo/seed")
    async def seed_demo(user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await seed_demo_data(session)

    return router
