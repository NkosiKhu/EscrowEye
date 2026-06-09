from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.hcs_service import HCSService
from app.infrastructure.models import AuditEvent, Job, User


async def get_job(session: AsyncSession, job_id: int) -> Job:
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    return job


async def get_user(session: AsyncSession, user_id: int) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="not_found")
    return user


def mock_cid(content: bytes, filename: str) -> str:
    digest = hashlib.sha256(filename.encode() + b":" + content).hexdigest()
    return "bafy" + digest[:45]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def add_audit(
    session: AsyncSession,
    job_id: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
    tx_hash: str | None = None,
) -> None:
    event_payload = payload or {}
    job_row = await session.execute(select(Job.hcs_topic_id).where(Job.id == job_id))
    hcs_topic = job_row.scalar_one_or_none()
    hcs_result = HCSService().submit_event(
        event_type,
        {"job_id": job_id, **event_payload},
        hcs_topic if hcs_topic else None,
    )
    seq_result = await session.execute(
        select(func.coalesce(func.max(AuditEvent.sequence_number), 0) + 1).where(AuditEvent.job_id == job_id)
    )
    seq_val = seq_result.scalar() or 1
    audit = AuditEvent(
        job_id=job_id,
        type=event_type,
        tx_hash=tx_hash or hcs_result.tx_id,
        sequence_number=seq_val,
        consensus_timestamp=now_iso(),
        hcs_status=hcs_result.status,
        payload_json=str(event_payload),
    )
    session.add(audit)


async def audit_events(session: AsyncSession, job_id: int) -> dict[str, Any]:
    job = await get_job(session, job_id)
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.job_id == job_id)
        .order_by(AuditEvent.sequence_number)
    )
    rows = result.scalars().all()
    events = []
    for row in rows:
        item = {
            "type": row.type,
            "job_id": row.job_id,
            "tx_hash": row.tx_hash,
            "sequence_number": row.sequence_number,
            "consensus_timestamp": row.consensus_timestamp,
        }
        if item["tx_hash"] is None:
            del item["tx_hash"]
        events.append(item)
    return {"hcs_topic_id": job.hcs_topic_id, "events": events}
