from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.services.job_service import JobService, PAYMENT_REQUIREMENTS


class JobIn(BaseModel):
    home_id: int
    title: str
    description: str
    suggested_price_tinybar: int
    access_notes: Optional[str] = None
    available_times: Optional[str] = None


class BidIn(BaseModel):
    amount_tinybar: int
    message: Optional[str] = None


class AwardIn(BaseModel):
    bid_id: int


class ReadyIn(BaseModel):
    message: Optional[str] = None


class DisputeIn(BaseModel):
    reason: str


class MessageIn(BaseModel):
    body: str = ""
    photo_ids: list[int] = Field(default_factory=list)


class PhotoPatch(BaseModel):
    room_id: Optional[int] = None
    review_status: Optional[str] = Field(default=None, pattern="^(pending|passed|failed|needs_retake)$")
    review_notes: Optional[str] = None


def create_jobs_router(
    *,
    db: Callable,
    one: Callable,
    now_iso: Callable[[], str],
    current_user: Callable,
    public_user: Callable,
    add_audit: Callable,
    base_dir: Path,
    upload_dir: Path,
    openrouter_api_key: str | None,
    openrouter_model: str,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["jobs"])

    def service(conn) -> JobService:
        return JobService(
            conn,
            one=one,
            now_iso=now_iso,
            public_user=public_user,
            add_audit=add_audit,
            base_dir=base_dir,
            upload_dir=upload_dir,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
        )

    @router.get("/jobs")
    def list_jobs(status: str | None = None, role: str | None = None, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).list_jobs(status, role, user)

    @router.post("/jobs", status_code=201)
    def create_job(
        body: JobIn,
        request: Request,
        x_payment: str | None = Header(default=None),
        x_402_payment: str | None = Header(default=None),
        user: dict[str, Any] = Depends(current_user),
    ):
        if not (x_payment or x_402_payment or request.headers.get("Payment")):
            return JSONResponse(status_code=402, content={"error": "payment_required", "payment_requirements": PAYMENT_REQUIREMENTS})
        with db() as conn:
            return service(conn).create_job(body, user)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).job_detail(job_id)

    @router.get("/jobs/{job_id}/bids")
    def list_bids(job_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).list_bids(job_id)

    @router.post("/jobs/{job_id}/bids")
    def create_bid(job_id: int, body: BidIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).create_bid(job_id, body, user)

    @router.put("/bids/{bid_id}")
    def update_bid(bid_id: int, body: BidIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).update_bid(bid_id, body, user)

    @router.delete("/bids/{bid_id}", status_code=204)
    def delete_bid(bid_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            service(conn).delete_bid(bid_id, user)
        return Response(status_code=204)

    @router.post("/jobs/{job_id}/award")
    def award_job(job_id: int, body: AwardIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).award_job(job_id, body.bid_id, user)

    @router.post("/jobs/{job_id}/fund")
    def fund_job(job_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = body
        with db() as conn:
            return service(conn).fund_job(job_id, user)

    @router.post("/jobs/{job_id}/mark-ready")
    def mark_ready(job_id: int, body: ReadyIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).mark_ready(job_id, body.message, user)

    @router.post("/jobs/{job_id}/confirm")
    def confirm_job(job_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
        _ = body
        with db() as conn:
            return service(conn).confirm_job(job_id, user)

    @router.post("/jobs/{job_id}/dispute")
    def dispute_job(job_id: int, body: DisputeIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).dispute_job(job_id, body.reason, user)

    @router.get("/jobs/{job_id}/messages")
    def list_messages(job_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).list_messages(job_id)

    @router.post("/jobs/{job_id}/messages")
    def create_message(job_id: int, body: MessageIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).create_message(job_id, body.body, body.photo_ids, user)

    @router.post("/jobs/{job_id}/photos")
    async def upload_photos(
        job_id: int,
        photos: list[UploadFile] = File(...),
        room_id: int | None = Form(default=None),
        encrypted_keys: str | None = Form(default=None),
        user: dict[str, Any] = Depends(current_user),
    ):
        results = []
        with db() as conn:
            job_service = service(conn)
            for upload in photos:
                results.append(
                    job_service.create_photo_record(
                        job_id,
                        room_id,
                        user["id"],
                        await upload.read(),
                        upload.filename or "photo",
                        upload.content_type,
                        encrypted_keys,
                    )
                )
        return {"photos": results}

    @router.get("/jobs/{job_id}/photos")
    def list_photos(job_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).list_photos(job_id)

    @router.patch("/jobs/{job_id}/photos/{photo_id}")
    def patch_photo(job_id: int, photo_id: int, body: PhotoPatch, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).patch_photo(job_id, photo_id, body)

    @router.get("/jobs/{job_id}/audit-events")
    def audit_events(job_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        with db() as conn:
            return service(conn).audit_events(job_id)

    return router
