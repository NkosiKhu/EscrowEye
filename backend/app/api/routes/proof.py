from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.services.proof_service import ProofService


class ProofPatch(BaseModel):
    room_id: int | None = None
    review_status: str | None = Field(default=None, pattern="^(pending|passed|failed|needs_retake)$")
    review_notes: str | None = None


def create_proof_router(
    *,
    db: Callable,
    now_iso: Callable[[], str],
    current_user: Callable,
    upload_dir: Path,
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["proof"])

    def service(session) -> ProofService:
        return ProofService(session, now_iso=now_iso, upload_dir=upload_dir)

    @router.post("/service-requests/{request_id}/proof", status_code=201)
    async def upload_service_proof(
        request_id: int,
        files: list[UploadFile] = File(...),
        room_or_area_label: str | None = Form(default=None),
        notes: str | None = Form(default=None),
        user: dict[str, Any] = Depends(current_user),
    ):
        results = []
        upload_dir.mkdir(parents=True, exist_ok=True)
        async with db() as session:
            proof_service = service(session)
            for upload in files:
                results.append(
                    await proof_service.create_proof_record(
                        request_id,
                        user["id"],
                        await upload.read(),
                        upload.filename or "proof",
                        upload.content_type,
                        room_or_area_label,
                        notes,
                    )
                )
            await proof_service.mark_uploaded(request_id, len(results))
        return {"proof": results}

    @router.get("/service-requests/{request_id}/proof")
    async def list_service_proof(request_id: int, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await service(session).list_proof(request_id)

    @router.patch("/service-requests/{request_id}/proof/{proof_id}")
    async def update_service_proof(request_id: int, proof_id: int, body: ProofPatch, user: dict[str, Any] = Depends(current_user)):
        _ = user
        async with db() as session:
            return await service(session).update_proof(request_id, proof_id, body)

    return router
