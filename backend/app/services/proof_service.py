from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.models import Job, Photo, ProofUpload, Room
from app.services._base import add_audit, mock_cid


logger = get_logger("escroweye.proof")


class ProofService:
    def __init__(self, session: AsyncSession, *, now_iso: Callable[[], str], upload_dir: Path):
        self.session = session
        self.now_iso = now_iso
        self.upload_dir = upload_dir

    async def create_proof_record(self, request_id: int, user_id: int, content: bytes, filename: str, content_type: str | None, room_or_area_label: str | None, notes: str | None) -> dict[str, Any]:
        result = await self.session.execute(select(Job).where(Job.id == request_id))
        result.scalar_one_or_none()
        seq_result = await self.session.execute(
            select(func.coalesce(func.max(Photo.sequence), 0)).where(Photo.job_id == request_id)
        )
        seq = (seq_result.scalar() or 0) + 1
        cid = mock_cid(content, filename)
        suffix = Path(filename or "proof.bin").suffix or ".bin"
        storage_path = self.upload_dir / f"request-{request_id}-proof-{seq}-{cid[:16]}{suffix}"
        storage_path.write_bytes(content)
        now = self.now_iso()

        photo = Photo(
            job_id=request_id,
            room_id=None,
            uploaded_by_user_id=user_id,
            cid=cid,
            filename=filename or storage_path.name,
            content_type=content_type,
            storage_path=str(storage_path),
            sequence=seq,
            review_status="pending",
            review_notes=notes or room_or_area_label,
            encrypted_keys="{}",
            created_at=now,
        )
        self.session.add(photo)
        await self.session.flush()

        proof = ProofUpload(
            job_id=request_id,
            photo_id=photo.id,
            uploaded_by_user_id=user_id,
            file_type="video" if (content_type or "").startswith("video/") else "image",
            storage_url=str(storage_path),
            cid=cid,
            room_or_area_label=room_or_area_label,
            notes=notes,
            validation_status="pending",
            created_at=now,
        )
        self.session.add(proof)

        logger.info("proof.uploaded request_id=%s photo_id=%s user_id=%s cid=%s content_type=%s", request_id, photo.id, user_id, cid, content_type)
        return {"id": photo.id, "cid": cid, "sequence": seq, "validation_status": "pending"}

    async def mark_uploaded(self, request_id: int, count: int) -> None:
        now = self.now_iso()
        result = await self.session.execute(select(Job).where(Job.id == request_id))
        job = result.scalar_one_or_none()
        if job is not None:
            job.status = "proof_uploaded"
            job.updated_at = now
        await add_audit(self.session, request_id, "proof_uploaded", {"count": count})

    async def list_proof(self, request_id: int) -> dict[str, Any]:
        result = await self.session.execute(
            select(ProofUpload).where(ProofUpload.job_id == request_id).order_by(ProofUpload.id)
        )
        rows = result.scalars().all()
        return {"proof": [{c.name: getattr(r, c.name) for c in ProofUpload.__table__.columns} for r in rows]}

    async def update_proof(self, request_id: int, proof_id: int, body: Any) -> dict[str, Any]:
        result = await self.session.execute(
            select(ProofUpload).where(ProofUpload.id == proof_id, ProofUpload.job_id == request_id)
        )
        proof = result.scalar_one_or_none()
        if proof is None:
            raise HTTPException(status_code=404, detail="not_found")
        if body.room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == body.room_id))
            room_result.scalar_one_or_none()
        photo_result = await self.session.execute(select(Photo).where(Photo.id == proof.photo_id))
        photo = photo_result.scalar_one_or_none()
        if photo is not None:
            if body.room_id is not None:
                photo.room_id = body.room_id
            if body.review_status is not None:
                photo.review_status = body.review_status
            if body.review_notes is not None:
                photo.review_notes = body.review_notes
        if body.review_status is not None:
            proof.validation_status = body.review_status
        room = None
        if photo is not None and photo.room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == photo.room_id))
            room_row = room_result.scalar_one_or_none()
            room = {"id": room_row.id, "name": room_row.name} if room_row else None
        return {
            "id": proof_id,
            "photo_id": proof.photo_id,
            "job_id": request_id,
            "room": room,
            "review_status": photo.review_status if photo else None,
            "review_notes": photo.review_notes if photo else None,
        }
