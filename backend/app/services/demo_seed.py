from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import AuditEvent, Bid, Home, Job, User


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def seed_demo_data(session: AsyncSession) -> dict[str, int]:
    now = _now()

    result = await session.execute(select(User).where(User.hedera_account_id == "0.0.1111"))
    owner = result.scalar_one_or_none()
    if owner is None:
        owner = User(
            email="owner@example.com",
            user_type="owner",
            hedera_account_id="0.0.1111",
            hedera_public_key="demo-owner-key",
            created_at=now,
        )
        session.add(owner)
        await session.flush()
    owner_id = owner.id

    result = await session.execute(select(User).where(User.hedera_account_id == "0.0.2222"))
    supplier = result.scalar_one_or_none()
    if supplier is None:
        supplier = User(
            email="supplier@example.com",
            user_type="supplier",
            hedera_account_id="0.0.2222",
            hedera_public_key="demo-supplier-key",
            created_at=now,
        )
        session.add(supplier)
        await session.flush()
    supplier_id = supplier.id

    result = await session.execute(select(Job).where(Job.title == "Demo window cleaning escrow"))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return {"owner_id": owner_id, "supplier_id": supplier_id, "job_id": existing.id}

    home = Home(
        owner_user_id=owner_id,
        name="Demo property",
        address="10b Gerrard Road, Ikoyi, Lagos",
        created_at=now,
        updated_at=now,
    )
    session.add(home)
    await session.flush()
    home_id = home.id

    job = Job(
        home_id=home_id,
        owner_user_id=owner_id,
        supplier_user_id=supplier_id,
        title="Demo window cleaning escrow",
        description="Clean windows and upload proof for AI validation.",
        suggested_price_tinybar=220000000,
        access_notes="Gate code 1234",
        available_times="Sat, 1 Mar 2025",
        status="escrow_funded",
        hcs_topic_id="0.0.88901",
        creation_fee_paid=True,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    job_id = job.id

    bid = Bid(
        job_id=job_id,
        supplier_user_id=supplier_id,
        amount_tinybar=220000000,
        message="Demo quote",
        status="accepted",
        created_at=now,
        updated_at=now,
    )
    session.add(bid)
    await session.flush()

    job.accepted_bid_id = bid.id
    job.escrow_account_id = f"0.0.{99000 + job_id}"

    audit = AuditEvent(
        job_id=job_id,
        type="demo_seeded",
        tx_hash="local:demo_seeded",
        sequence_number=1,
        consensus_timestamp=now,
    )
    session.add(audit)

    return {"owner_id": owner_id, "supplier_id": supplier_id, "job_id": job_id}
