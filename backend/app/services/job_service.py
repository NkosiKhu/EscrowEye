from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Bid, Home, Job, Message, MessagePhoto, Photo, Room, User
from app.services._base import audit_events as base_audit_events
from app.services._base import get_job, get_user, mock_cid


class JobService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now_iso: Callable[[], str],
        public_user: Callable,
        add_audit: Callable,
        base_dir: Path,
        upload_dir: Path,
        openrouter_api_key: str | None,
        openrouter_model: str,
    ):
        self.session = session
        self.now_iso = now_iso
        self.public_user = public_user
        self.add_audit = add_audit
        self.base_dir = base_dir
        self.upload_dir = upload_dir
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_model = openrouter_model

    async def job_summary(self, job: Job) -> dict[str, Any]:
        home_result = await self.session.execute(select(Home).where(Home.id == job.home_id))
        home = home_result.scalar_one_or_none()
        owner = await get_user(self.session, job.owner_user_id)
        supplier = None
        if job.supplier_user_id is not None:
            supplier_result = await self.session.execute(select(User).where(User.id == job.supplier_user_id))
            supplier = supplier_result.scalar_one_or_none()
        bid_result = await self.session.execute(select(func.count(Bid.id), func.min(Bid.amount_tinybar)).where(Bid.job_id == job.id, Bid.status != "withdrawn"))
        bid_row = bid_result.one()
        bid_count = bid_row[0] or 0
        min_bid = bid_row[1]
        return {
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "suggested_price_tinybar": job.suggested_price_tinybar,
            "status": job.status,
            "home": {"id": home.id, "name": home.name, "address": home.address} if home else {"id": job.home_id, "name": "Service address", "address": ""},
            "owner": {"id": owner.id, "hedera_account_id": owner.hedera_account_id},
            "supplier": self.public_user(
                {
                    "id": supplier.id,
                    "email": supplier.email,
                    "user_type": supplier.user_type,
                    "hedera_account_id": supplier.hedera_account_id,
                    "hedera_public_key": supplier.hedera_public_key,
                }
                if supplier
                else None
            ),
            "bid_count": bid_count,
            "lowest_bid_tinybar": min_bid,
            "created_at": job.created_at,
        }

    async def job_detail(self, job_id: int) -> dict[str, Any]:
        job = await get_job(self.session, job_id)
        data = await self.job_summary(job)
        accepted = None
        if job.accepted_bid_id is not None:
            bid_result = await self.session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
            accepted = bid_result.scalar_one_or_none()
        data.update(
            {
                "access_notes": job.access_notes,
                "available_times": job.available_times,
                "escrow_account_id": job.escrow_account_id,
                "hcs_topic_id": job.hcs_topic_id,
                "accepted_bid": {"id": accepted.id, "amount_tinybar": accepted.amount_tinybar} if accepted else None,
                "creation_fee_paid": bool(job.creation_fee_paid),
                "updated_at": job.updated_at,
            }
        )
        return data

    async def bid_payload(self, bid: Bid) -> dict[str, Any]:
        supplier = await get_user(self.session, bid.supplier_user_id)
        return {
            "id": bid.id,
            "supplier": {"id": supplier.id, "hedera_account_id": supplier.hedera_account_id},
            "amount_tinybar": bid.amount_tinybar,
            "message": bid.message,
            "status": bid.status,
            "created_at": bid.created_at,
        }

    async def insert_message(self, job_id: int, sender_user_id: int | None, sender_type: str, body: str, photo_ids: list[int]) -> Message:
        msg = Message(
            job_id=job_id,
            sender_user_id=sender_user_id,
            sender_type=sender_type,
            body=body,
            created_at=self.now_iso(),
        )
        self.session.add(msg)
        await self.session.flush()
        for photo_id in photo_ids:
            photo_result = await self.session.execute(select(Photo).where(Photo.id == photo_id, Photo.job_id == job_id))
            photo_result.scalar_one_or_none()
            mp = MessagePhoto(message_id=msg.id, photo_id=photo_id)
            self.session.add(mp)
        await self.session.flush()
        msg_result = await self.session.execute(select(Message).where(Message.id == msg.id))
        return msg_result.scalar_one()

    async def message_payload(self, msg: Message) -> dict[str, Any]:
        sender = None
        if msg.sender_user_id is not None:
            sender_result = await self.session.execute(select(User).where(User.id == msg.sender_user_id))
            sender = sender_result.scalar_one_or_none()
        photo_rows_result = await self.session.execute(
            select(Photo.id, Photo.cid, Photo.sequence)
            .join(MessagePhoto, MessagePhoto.photo_id == Photo.id)
            .where(MessagePhoto.message_id == msg.id)
            .order_by(Photo.sequence)
        )
        photo_rows = photo_rows_result.all()
        return {
            "id": msg.id,
            "sender_user_id": msg.sender_user_id,
            "sender": self.public_user(
                {
                    "id": sender.id,
                    "email": sender.email,
                    "user_type": sender.user_type,
                    "hedera_account_id": sender.hedera_account_id,
                    "hedera_public_key": sender.hedera_public_key,
                }
                if sender
                else None
            ),
            "sender_type": msg.sender_type,
            "body": msg.body,
            "photo_ids": [p.id for p in photo_rows],
            "photos": [{"id": p.id, "cid": p.cid, "sequence": p.sequence} for p in photo_rows],
            "created_at": msg.created_at,
        }

    async def list_jobs(self, status: str | None, role: str | None, user: dict[str, Any]) -> dict[str, Any]:
        stmt = select(Job)
        if status:
            stmt = stmt.where(Job.status == status)
        if role == "owned":
            stmt = stmt.where(Job.owner_user_id == user["id"])
        elif role == "assigned":
            stmt = stmt.where(Job.supplier_user_id == user["id"])
        stmt = stmt.order_by(Job.id.desc())
        result = await self.session.execute(stmt)
        jobs = result.scalars().all()
        results = []
        for job in jobs:
            results.append(await self.job_summary(job))
        return {"jobs": results}

    async def create_job(self, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        home_result = await self.session.execute(select(Home).where(Home.id == body.home_id, Home.owner_user_id == user["id"]))
        if home_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="not_found")
        now = self.now_iso()
        hcs_topic = f"0.0.{88880 + int(time.time()) % 10000}"
        job = Job(
            home_id=body.home_id,
            owner_user_id=user["id"],
            title=body.title,
            description=body.description,
            suggested_price_tinybar=body.suggested_price_tinybar,
            access_notes=body.access_notes,
            available_times=body.available_times,
            status="bidding",
            hcs_topic_id=hcs_topic,
            creation_fee_paid=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        await self.session.flush()
        await self.add_audit(self.session, job.id, "job_created")
        return {"id": job.id, "status": "bidding", "creation_fee_paid": True, "hcs_topic_id": hcs_topic}

    async def list_bids(self, job_id: int) -> dict[str, Any]:
        await get_job(self.session, job_id)
        result = await self.session.execute(select(Bid).where(Bid.job_id == job_id, Bid.status != "withdrawn").order_by(Bid.amount_tinybar))
        bids = result.scalars().all()
        results = []
        for bid in bids:
            results.append(await self.bid_payload(bid))
        return {"bids": results}

    async def create_bid(self, job_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        await get_job(self.session, job_id)
        now = self.now_iso()
        bid = Bid(
            job_id=job_id,
            supplier_user_id=user["id"],
            amount_tinybar=body.amount_tinybar,
            message=body.message,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        self.session.add(bid)
        await self.session.flush()
        return {"id": bid.id, "amount_tinybar": body.amount_tinybar, "status": "pending"}

    async def update_bid(self, bid_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.execute(select(Bid).where(Bid.id == bid_id, Bid.supplier_user_id == user["id"]))
        bid = result.scalar_one_or_none()
        if bid is None:
            raise HTTPException(status_code=404, detail="not_found")
        if bid.status != "pending":
            raise HTTPException(status_code=409, detail="bid_not_editable")
        bid.amount_tinybar = body.amount_tinybar
        bid.message = body.message
        bid.updated_at = self.now_iso()
        await self.session.flush()
        return {"id": bid_id, "amount_tinybar": body.amount_tinybar, "status": "pending"}

    async def delete_bid(self, bid_id: int, user: dict[str, Any]) -> None:
        result = await self.session.execute(select(Bid).where(Bid.id == bid_id, Bid.supplier_user_id == user["id"]))
        bid = result.scalar_one_or_none()
        if bid is None:
            raise HTTPException(status_code=404, detail="not_found")
        bid.status = "withdrawn"
        bid.updated_at = self.now_iso()

    async def award_job(self, job_id: int, bid_id: int, user: dict[str, Any]) -> dict[str, Any]:
        job_result = await self.session.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user["id"]))
        job = job_result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="not_found")
        bid_result = await self.session.execute(select(Bid).where(Bid.id == bid_id, Bid.job_id == job_id, Bid.status == "pending"))
        bid = bid_result.scalar_one_or_none()
        if bid is None:
            raise HTTPException(status_code=404, detail="not_found")
        now = self.now_iso()
        bids_result = await self.session.execute(select(Bid).where(Bid.job_id == job_id))
        for b in bids_result.scalars().all():
            b.status = "accepted" if b.id == bid_id else "rejected"
        job.supplier_user_id = bid.supplier_user_id
        job.accepted_bid_id = bid_id
        job.status = "awarded"
        job.updated_at = now
        supplier = await get_user(self.session, bid.supplier_user_id)
        return {
            "job_id": job_id,
            "status": "awarded",
            "supplier": self.public_user(
                {
                    "id": supplier.id,
                    "email": supplier.email,
                    "user_type": supplier.user_type,
                    "hedera_account_id": supplier.hedera_account_id,
                    "hedera_public_key": supplier.hedera_public_key,
                }
            ),
        }

    async def fund_job(self, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
        job_result = await self.session.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user["id"]))
        job = job_result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="not_found")
        if job.accepted_bid_id is None:
            raise HTTPException(status_code=409, detail="no_accepted_bid")
        bid_result = await self.session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
        bid = bid_result.scalar_one()
        escrow = f"0.0.{99990 + job_id}"
        now = self.now_iso()
        job.status = "funded"
        job.escrow_account_id = escrow
        job.updated_at = now
        return {"job_id": job_id, "status": "funded", "escrow_account_id": escrow, "amount_tinybar": bid.amount_tinybar}

    async def mark_ready(self, job_id: int, message: str | None, user: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.execute(select(Job).where(Job.id == job_id, Job.supplier_user_id == user["id"]))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="not_found")
        now = self.now_iso()
        job.status = "awaiting_confirmation"
        job.updated_at = now
        if message:
            await self.insert_message(job_id, user["id"], "human", message, [])
        return {"job_id": job_id, "status": "awaiting_confirmation"}

    async def confirm_job(self, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
        tx_hash = f"{user['hedera_account_id']}@{int(time.time())}.000000000"
        result = await self.session.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user["id"]))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="not_found")
        now = self.now_iso()
        job.status = "completed"
        job.updated_at = now
        await self.add_audit(self.session, job_id, "job_completed", tx_hash)
        return {"job_id": job_id, "status": "completed", "tx_hash": tx_hash}

    async def dispute_job(self, job_id: int, reason: str, user: dict[str, Any]) -> dict[str, Any]:
        await get_job(self.session, job_id)
        now = self.now_iso()
        job_result = await self.session.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()
        job.status = "disputed"
        job.updated_at = now
        await self.add_audit(self.session, job_id, "job_disputed")
        await self.insert_message(job_id, user["id"], "human", reason, [])
        return {"job_id": job_id, "status": "disputed"}

    async def list_messages(self, job_id: int) -> dict[str, Any]:
        await get_job(self.session, job_id)
        result = await self.session.execute(select(Message).where(Message.job_id == job_id).order_by(Message.id))
        rows = result.scalars().all()
        results = []
        for row in rows:
            results.append(await self.message_payload(row))
        return {"messages": results}

    async def create_message(self, job_id: int, body: str, photo_ids: list[int], user: dict[str, Any]) -> dict[str, Any]:
        await get_job(self.session, job_id)
        msg = await self.insert_message(job_id, user["id"], "human", body, photo_ids)
        if photo_ids:
            await self.review_photos(job_id, photo_ids)
        return {
            "id": msg.id,
            "sender_user_id": user["id"],
            "sender_type": "human",
            "body": msg.body,
            "photo_ids": photo_ids,
            "created_at": msg.created_at,
        }

    async def create_photo_record(
        self, job_id: int, room_id: int | None, user_id: int, content: bytes, filename: str, content_type: str | None, encrypted_keys: str | None
    ) -> dict[str, Any]:
        await get_job(self.session, job_id)
        if room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == room_id))
            if room_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="room_not_found")
        seq_result = await self.session.execute(select(func.coalesce(func.max(Photo.sequence), 0)).where(Photo.job_id == job_id))
        seq = (seq_result.scalar() or 0) + 1
        cid = mock_cid(content, filename)
        suffix = Path(filename or "photo.bin").suffix or ".bin"
        storage_path = self.upload_dir / f"job-{job_id}-photo-{seq}-{cid[:16]}{suffix}"
        storage_path.write_bytes(content)
        try:
            stored_path = str(storage_path.relative_to(self.base_dir))
        except ValueError:
            stored_path = str(storage_path)
        now = self.now_iso()
        photo = Photo(
            job_id=job_id,
            room_id=room_id,
            uploaded_by_user_id=user_id,
            cid=cid,
            filename=filename or storage_path.name,
            content_type=content_type,
            storage_path=stored_path,
            sequence=seq,
            review_status="pending",
            encrypted_keys=encrypted_keys,
            created_at=now,
        )
        self.session.add(photo)
        await self.session.flush()
        return {"id": photo.id, "cid": cid, "sequence": seq, "review_status": "pending"}

    async def photo_payload(self, photo: Photo) -> dict[str, Any]:
        room = None
        if photo.room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == photo.room_id))
            room_row = room_result.scalar_one_or_none()
            room = {"id": room_row.id, "name": room_row.name} if room_row else None
        uploaded_by = await get_user(self.session, photo.uploaded_by_user_id)
        return {
            "id": photo.id,
            "cid": photo.cid,
            "room": room,
            "uploaded_by": {"id": uploaded_by.id, "hedera_account_id": uploaded_by.hedera_account_id},
            "sequence": photo.sequence,
            "review_status": photo.review_status,
            "review_notes": photo.review_notes,
            "created_at": photo.created_at,
        }

    async def list_photos(self, job_id: int) -> dict[str, Any]:
        await get_job(self.session, job_id)
        result = await self.session.execute(select(Photo).where(Photo.job_id == job_id).order_by(Photo.sequence))
        rows = result.scalars().all()
        results = []
        for row in rows:
            results.append(await self.photo_payload(row))
        return {"photos": results}

    async def patch_photo(self, job_id: int, photo_id: int, body: Any) -> dict[str, Any]:
        result = await self.session.execute(select(Photo).where(Photo.id == photo_id, Photo.job_id == job_id))
        photo = result.scalar_one_or_none()
        if photo is None:
            raise HTTPException(status_code=404, detail="not_found")
        if body.room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == body.room_id))
            if room_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="room_not_found")
        if body.room_id is not None:
            photo.room_id = body.room_id
        if body.review_status is not None:
            photo.review_status = body.review_status
        if body.review_notes is not None:
            photo.review_notes = body.review_notes
        await self.session.flush()
        room = None
        if photo.room_id is not None:
            room_result = await self.session.execute(select(Room).where(Room.id == photo.room_id))
            room_row = room_result.scalar_one_or_none()
            room = {"id": room_row.id, "name": room_row.name} if room_row else None
        return {
            "id": photo_id,
            "job_id": job_id,
            "room": room,
            "review_status": photo.review_status,
            "review_notes": photo.review_notes,
        }

    async def audit_events(self, job_id: int) -> dict[str, Any]:
        return await base_audit_events(self.session, job_id)

    async def review_photos(self, job_id: int, photo_ids: list[int]) -> None:
        rooms_result = await self.session.execute(select(Room).join(Job, Job.home_id == Room.home_id).where(Job.id == job_id).order_by(Room.id))
        rooms = rooms_result.scalars().all()
        photos_result = await self.session.execute(select(Photo).where(Photo.job_id == job_id, Photo.id.in_(photo_ids)).order_by(Photo.sequence))
        photos = photos_result.scalars().all()
        failures: list[str] = []
        for index, photo in enumerate(photos):
            filename = (photo.filename or "").lower()
            room = next((r for r in rooms if r.name.lower() in filename), None)
            if room is None and rooms:
                room = rooms[index % len(rooms)]

            model_result = await self.openrouter_review_photo(job_id, rooms, photo)
            if model_result:
                model_room_id = model_result.get("room_id")
                matched_room = next((r for r in rooms if r.id == model_room_id), None)
                if matched_room is not None:
                    room = matched_room
                failed = not bool(model_result.get("pass"))
                issues = model_result.get("issues")
                issue_text = ", ".join(str(i) for i in issues) if isinstance(issues, list) and issues else "review did not pass"
                status = "needs_retake" if failed else "passed"
                room_name = room.name if room else str(model_result.get("room_name") or "the uploaded area")
                notes = f"{room_name} {'needs a retake: ' + issue_text if failed else 'looks clean based on OpenRouter review.'}"
            else:
                bad_words = ("dirty", "mess", "retake", "fail", "stain", "trash", "before")
                failed = any(word in filename for word in bad_words)
                status = "needs_retake" if failed else "passed"
                room_name = room.name if room else "the uploaded area"
                notes = f"{room_name} {'needs a retake based on mock review heuristics.' if failed else 'looks clean in the mock review.'}"
            photo.room_id = room.id if room else None
            photo.review_status = status
            photo.review_notes = notes
            if failed:
                failures.append(f"{room_name} needs a retake")
        summary = "Photo review: " + "; ".join(failures) + "." if failures else "Photo review: all uploaded rooms look clean. Ready for owner review."
        await self.insert_message(job_id, None, "agent", summary, [])
        await self.insert_message(job_id, None, "system", "Automated photo review completed.", [])

    async def openrouter_review_photo(self, job_id: int, rooms: Sequence[Room], photo: Photo) -> dict[str, Any] | None:
        if not self.openrouter_api_key:
            return None
        path = self.base_dir / photo.storage_path
        if not path.exists():
            return None
        room_list = [{"id": r.id, "name": r.name} for r in rooms]
        image_data = base64.b64encode(path.read_bytes()).decode()
        mime_type = photo.content_type or "image/jpeg"
        prompt = (
            f"You are evaluating a cleaning photo for EscrowEye job #{job_id}.\n"
            f"Rooms to clean: {json.dumps(room_list)}\n"
            "Return JSON only with keys: room_id, room_name, confidence, cleanliness_score, pass, issues. "
            "Use one of the provided room ids when possible. pass must be true only when cleanliness_score is at least 4."
        )
        payload = {
            "model": self.openrouter_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}],
                }
            ],
        }
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "EscrowEye Local MVP",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.loads(response.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        if not isinstance(content, str):
            return None
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
