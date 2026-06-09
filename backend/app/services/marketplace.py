from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import AIValidationStatus, EscrowStatus, JobStatus
from app.services.escrow import EscrowService
from app.infrastructure.models import (
    AIValidation,
    Bid,
    EscrowTransaction,
    Home,
    Job,
    Message,
    Photo,
    User,
)
from app.services._base import add_audit, get_job, get_user

logger = get_logger("escroweye.marketplace")


SERVICE_CATEGORIES = [
    {"id": 1, "name": "Cleaning", "slug": "cleaning", "description": "Home, office, and post-construction cleaning"},
    {"id": 2, "name": "Pool cleaning", "slug": "pool-cleaning", "description": "Pool cleaning and water maintenance"},
    {"id": 3, "name": "Maintenance", "slug": "maintenance", "description": "General property maintenance"},
    {"id": 4, "name": "Airbnb turnover", "slug": "airbnb", "description": "Short-let cleaning and reset services"},
    {"id": 5, "name": "Carpentry", "slug": "carpentry", "description": "Carpentry, fittings, and repairs"},
    {"id": 6, "name": "Plumbing", "slug": "plumbing", "description": "Leaks, fixtures, and pipe work"},
    {"id": 7, "name": "Electrical repairs", "slug": "electrical-repairs", "description": "Electrical diagnostics and repairs"},
    {"id": 8, "name": "Handyman", "slug": "handyman", "description": "Small repairs and odd jobs"},
]


WORKERS = [
    {
        "id": 1,
        "supplier_id": 1,
        "name": "Chijioke Nwosu",
        "profession": "Expert window washing",
        "rating": 4.8,
        "average_rate": "From \u20a680k",
        "location": "Ikoyi",
        "profile_image": "https://images.unsplash.com/photo-1503387762-592deb58ef4e?auto=format&fit=crop&w=500&q=80",
        "completed_jobs": 128,
        "services": ["cleaning", "airbnb"],
    },
    {
        "id": 2,
        "supplier_id": 2,
        "name": "Kurt Kanu",
        "profession": "Post-construction cleaning",
        "rating": 5.0,
        "average_rate": "From \u20a6120k",
        "location": "Victoria Island",
        "profile_image": "https://images.unsplash.com/photo-1580894894513-541e068a3e2b?auto=format&fit=crop&w=500&q=80",
        "completed_jobs": 91,
        "services": ["cleaning", "maintenance"],
    },
    {
        "id": 3,
        "supplier_id": 3,
        "name": "Favour Bello",
        "profession": "Airbnb turnover specialist",
        "rating": 4.9,
        "average_rate": "From \u20a665k",
        "location": "Surulere",
        "profile_image": "https://images.unsplash.com/photo-1565347878134-064b9185ced8?auto=format&fit=crop&w=500&q=80",
        "completed_jobs": 74,
        "services": ["airbnb", "cleaning"],
    },
]


def require_role(user: dict[str, Any], role: str) -> None:
    if user["user_type"] != role:
        raise HTTPException(status_code=403, detail=f"{role}_role_required")


def base_fee_for(amount: int) -> int:
    return round(amount * 0.2)


def category_by_slug(slug: str | None) -> dict[str, Any] | None:
    if not slug:
        return None
    return next((cat for cat in SERVICE_CATEGORIES if cat["slug"] == slug or cat["name"].lower() == slug.lower()), None)


def list_workers(category: str | None = None, location: str | None = None) -> list[dict[str, Any]]:
    workers = WORKERS
    if category:
        slug = (category_by_slug(category) or {"slug": category})["slug"]
        workers = [w for w in workers if slug in w["services"]]
    if location:
        needle = location.lower()
        workers = [w for w in workers if needle in w["location"].lower()]
    return workers


async def set_user_role(session: AsyncSession, user: dict[str, Any], role: str) -> dict[str, str]:
    if role not in {"owner", "supplier"}:
        raise HTTPException(status_code=422, detail="invalid_role")
    result = await session.execute(select(User).where(User.id == user["id"]))
    db_user = result.scalar_one_or_none()
    if db_user is not None:
        db_user.user_type = role
    logger.info("user.role_updated user_id=%s wallet=%s role=%s", user["id"], user["hedera_account_id"], role)
    return {"role": role}


async def setup_profile(session: AsyncSession, body: Any, user: dict[str, Any], public_user: Any) -> dict[str, Any]:
    result = await session.execute(select(User).where(User.id == user["id"]))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(status_code=404, detail="not_found")
    db_user.first_name = body.first_name
    db_user.last_name = body.last_name
    db_user.profile_photo_url = body.profile_photo_url
    db_user.location = body.location
    db_user.service_area = body.service_area
    db_user.payment_token_preference = body.payment_token_preference
    if user["user_type"] == "supplier":
        from app.infrastructure.models import SupplierProfile

        sp_result = await session.execute(select(SupplierProfile).where(SupplierProfile.user_id == user["id"]))
        sp = sp_result.scalar_one_or_none()
        if sp is None:
            sp = SupplierProfile(
                user_id=user["id"],
                services_offered="Cleaning, Maintenance",
                work_experience="3 years",
                portfolio_items="[]",
                average_rate="From \u20a680k",
                rating=4.8,
                reviews_count=0,
                verification_status="verified",
                created_at=db_user.created_at,
                updated_at=db_user.created_at,
            )
            session.add(sp)
    await session.flush()
    payload = public_user(
        {
            "id": db_user.id,
            "email": db_user.email,
            "user_type": db_user.user_type,
            "hedera_account_id": db_user.hedera_account_id,
            "hedera_public_key": db_user.hedera_public_key,
        }
    )
    payload.update(body.model_dump())
    return payload


async def list_service_requests(session: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
    if user["user_type"] == "owner":
        result = await session.execute(select(Job).where(Job.owner_user_id == user["id"]).order_by(Job.id.desc()))
    else:
        result = await session.execute(
            select(Job).where((Job.supplier_user_id == user["id"]) | Job.status.in_(["quote_requested", "quote_received"])).order_by(Job.id.desc())
        )
    jobs = result.scalars().all()
    results = []
    for job in jobs:
        results.append(await service_request_payload(session, job))
    return {"requests": results}


async def get_service_request(session: AsyncSession, request_id: int) -> dict[str, Any]:
    job = await get_job(session, request_id)
    return await service_request_payload(session, job)


async def update_service_request(session: AsyncSession, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    result = await session.execute(select(Job).where(Job.id == request_id, Job.owner_user_id == user["id"]))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    job.title = body.title
    job.description = body.description
    job.suggested_price_tinybar = body.budget_amount
    job.access_notes = body.location_description
    job.available_times = body.schedule
    await add_audit(session, request_id, "service_request_updated")
    return await get_service_request(session, request_id)


async def cancel_service_request(session: AsyncSession, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    result = await session.execute(select(Job).where(Job.id == request_id, Job.owner_user_id == user["id"]))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    job.status = "cancelled"
    await add_audit(session, request_id, "service_request_cancelled")
    return {"request_id": request_id, "status": "cancelled"}


async def supplier_accept_job(session: AsyncSession, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    await get_job(session, job_id)
    result = await session.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    job.supplier_user_id = user["id"]
    job.status = "accepted"
    await add_audit(session, job_id, "supplier_accepted")
    return {"job_id": job_id, "status": "accepted"}


async def supplier_mark_processing(session: AsyncSession, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    result = await session.execute(select(Job).where(Job.id == job_id, Job.supplier_user_id == user["id"]))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    job.status = "processing"
    await add_audit(session, job_id, "supplier_processing")
    return {"job_id": job_id, "status": "processing"}


async def supplier_mark_complete(session: AsyncSession, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    result = await session.execute(select(Job).where(Job.id == job_id, Job.supplier_user_id == user["id"]))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    job.status = "awaiting_owner_confirmation"
    await add_audit(session, job_id, "supplier_marked_complete")
    return {"job_id": job_id, "status": "awaiting_owner_confirmation"}


async def message_payload(session: AsyncSession, msg: Message) -> dict[str, Any]:
    sender = None
    if msg.sender_user_id is not None:
        sender_result = await session.execute(select(User).where(User.id == msg.sender_user_id))
        sender = sender_result.scalar_one_or_none()
    return {
        "id": msg.id,
        "sender_user_id": msg.sender_user_id,
        "sender": {"id": sender.id, "hedera_account_id": sender.hedera_account_id} if sender else None,
        "sender_type": msg.sender_type,
        "body": msg.body,
        "photo_ids": [],
        "photos": [],
        "created_at": msg.created_at,
    }


async def list_service_messages(session: AsyncSession, request_id: int) -> dict[str, Any]:
    await get_job(session, request_id)
    result = await session.execute(select(Message).where(Message.job_id == request_id).order_by(Message.id))
    messages = result.scalars().all()
    results = []
    for msg in messages:
        results.append(await message_payload(session, msg))
    return {"messages": results}


async def create_service_message(session: AsyncSession, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    await get_job(session, request_id)
    msg = Message(
        job_id=request_id,
        sender_user_id=user["id"],
        sender_type=body.type,
        body=body.body,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(msg)
    await session.flush()
    return await message_payload(session, msg)


async def list_request_quotes(session: AsyncSession, request_id: int) -> dict[str, Any]:
    result = await session.execute(select(Bid).where(Bid.job_id == request_id, Bid.status != "withdrawn").order_by(Bid.amount_tinybar))
    rows = result.scalars().all()
    results = []
    for row in rows:
        results.append(await quote_payload(session, row))
    return {"quotes": results}


async def reject_quote(session: AsyncSession, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid_result = await session.execute(select(Bid).where(Bid.id == quote_id))
    bid = bid_result.scalar_one_or_none()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    job_result = await session.execute(select(Job).where(Job.id == bid.job_id, Job.owner_user_id == user["id"]))
    if job_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=403, detail="owner_role_required")
    bid.status = "rejected"
    await add_audit(session, bid.job_id, "quote_rejected")
    return {"quote_id": quote_id, "status": "rejected"}


async def withdraw_quote(session: AsyncSession, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid_result = await session.execute(select(Bid).where(Bid.id == quote_id, Bid.supplier_user_id == user["id"]))
    bid = bid_result.scalar_one_or_none()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    bid.status = "withdrawn"
    await add_audit(session, bid.job_id, "quote_withdrawn")
    return {"quote_id": quote_id, "status": "withdrawn"}


async def pay_base_fee(session: AsyncSession, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job_result = await session.execute(select(Job).where(Job.id == request_id, Job.owner_user_id == user["id"]))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.accepted_bid_id is None:
        raise HTTPException(status_code=409, detail="quote_not_accepted")
    bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
    bid = bid_result.scalar_one()
    fee = base_fee_for(bid.amount_tinybar)
    await record_transaction(session, request_id, "base_fee", fee, "HBAR", "settled", f"local:base-fee:{request_id}")
    await add_audit(session, request_id, "base_fee_paid", {"amount": fee})
    logger.info("escrow.base_fee_paid request_id=%s owner_wallet=%s amount=%s", request_id, user["hedera_account_id"], fee)
    return {"request_id": request_id, "status": "base_fee_paid", "amount": fee}


async def service_escrow(session: AsyncSession, request_id: int) -> dict[str, Any]:
    job = await get_job(session, request_id)
    bid = None
    if job.accepted_bid_id is not None:
        bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
        bid = bid_result.scalar_one_or_none()
    return {
        "request_id": request_id,
        "escrow_account_id": job.escrow_account_id,
        "quote_amount": bid.amount_tinybar if bid else None,
        "base_commitment_fee": base_fee_for(bid.amount_tinybar) if bid else None,
        "escrow_status": "escrow_funded" if job.escrow_account_id else "escrow_pending",
    }


async def dispute_service_request(session: AsyncSession, request_id: int, reason: str, user: dict[str, Any]) -> dict[str, Any]:
    await get_job(session, request_id)
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one()
    job.status = "disputed"
    await add_audit(session, request_id, "dispute_opened", {"reason": reason, "user_id": user["id"]})
    return {"request_id": request_id, "status": "disputed"}


async def get_ai_validation(session: AsyncSession, request_id: int) -> dict[str, Any]:
    result = await session.execute(select(AIValidation).where(AIValidation.job_id == request_id).order_by(AIValidation.id.desc()))
    row = result.scalar_one_or_none()
    if row is None:
        return {"request_id": request_id, "status": "waiting_for_proof", "confidence_score": 0}
    return {c.name: getattr(row, c.name) for c in AIValidation.__table__.columns}


async def request_ai_corrections(session: AsyncSession, request_id: int, body: dict[str, Any]) -> dict[str, Any]:
    await get_job(session, request_id)
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one()
    job.status = "needs_revision"
    await add_audit(session, request_id, "ai_requested_corrections", body)
    return {"request_id": request_id, "status": "needs_more_evidence"}


async def hcs_topic(session: AsyncSession, request_id: int) -> dict[str, Any]:
    job = await get_job(session, request_id)
    return {"request_id": request_id, "hcs_topic_id": job.hcs_topic_id}


async def supplier_earnings(session: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    accepted_result = await session.execute(
        select(func.coalesce(func.sum(Bid.amount_tinybar), 0))
        .select_from(Bid)
        .join(Job, Job.accepted_bid_id == Bid.id)
        .where(Bid.supplier_user_id == user["id"], Job.status != "completed")
    )
    accepted_total = accepted_result.scalar() or 0
    paid_result = await session.execute(
        select(func.coalesce(func.sum(EscrowTransaction.amount), 0))
        .select_from(EscrowTransaction)
        .join(Job, Job.id == EscrowTransaction.job_id)
        .where(Job.supplier_user_id == user["id"], EscrowTransaction.type == "release")
    )
    paid_total = paid_result.scalar() or 0
    return {"pending_earnings": accepted_total, "past_earnings": paid_total, "total_earnings": accepted_total + paid_total}


async def supplier_transactions(session: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    result = await session.execute(
        select(EscrowTransaction).join(Job, Job.id == EscrowTransaction.job_id).where(Job.supplier_user_id == user["id"]).order_by(EscrowTransaction.id.desc())
    )
    rows = result.scalars().all()
    return {"transactions": [{c.name: getattr(r, c.name) for c in EscrowTransaction.__table__.columns} for r in rows]}


async def owner_payments(session: AsyncSession, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "owner")
    result = await session.execute(
        select(EscrowTransaction).join(Job, Job.id == EscrowTransaction.job_id).where(Job.owner_user_id == user["id"]).order_by(EscrowTransaction.id.desc())
    )
    rows = result.scalars().all()
    return {"payments": [{c.name: getattr(r, c.name) for c in EscrowTransaction.__table__.columns} for r in rows]}


async def create_request(session: AsyncSession, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "owner")
    now = datetime.now(UTC).isoformat()
    home = Home(
        owner_user_id=user["id"],
        name=body.title[:48],
        address=body.address,
        created_at=now,
        updated_at=now,
    )
    session.add(home)
    await session.flush()
    hcs_topic = f"0.0.{88880 + home.id}"
    job = Job(
        home_id=home.id,
        owner_user_id=user["id"],
        title=body.title,
        description=body.description,
        suggested_price_tinybar=body.budget_amount,
        access_notes=body.location_description,
        available_times=body.schedule,
        status=JobStatus.QUOTE_REQUESTED,
        hcs_topic_id=hcs_topic,
        creation_fee_paid=1,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()
    await add_audit(session, job.id, "service_request_created", {"category": body.category})
    logger.info(
        "service_request.created request_id=%s owner_wallet=%s category=%s budget=%s", job.id, user["hedera_account_id"], body.category, body.budget_amount
    )
    return {"id": job.id, "status": JobStatus.QUOTE_REQUESTED, "hcs_topic_id": hcs_topic}


async def quote_payload(session: AsyncSession, bid: Bid) -> dict[str, Any]:
    supplier = await get_user(session, bid.supplier_user_id) if bid.supplier_user_id else None
    return {
        "id": bid.id,
        "request_id": bid.job_id,
        "supplier_id": bid.supplier_user_id,
        "supplier": {"id": supplier.id, "hedera_account_id": supplier.hedera_account_id} if supplier else None,
        "amount": bid.amount_tinybar,
        "amount_tinybar": bid.amount_tinybar,
        "message": bid.message,
        "status": bid.status,
        "created_at": bid.created_at,
    }


async def create_quote(session: AsyncSession, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    await get_job(session, request_id)
    now = datetime.now(UTC).isoformat()
    bid = Bid(
        job_id=request_id,
        supplier_user_id=user["id"],
        amount_tinybar=body.amount,
        message=body.message,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    session.add(bid)
    await session.flush()
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one()
    job.status = JobStatus.QUOTE_RECEIVED
    job.updated_at = now
    await add_audit(session, request_id, "quote_submitted", {"amount": body.amount})
    logger.info("quote.created request_id=%s quote_id=%s supplier_wallet=%s amount=%s", request_id, bid.id, user["hedera_account_id"], body.amount)
    return await quote_payload(session, bid)


async def accept_quote(session: AsyncSession, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid_result = await session.execute(select(Bid).where(Bid.id == quote_id))
    bid = bid_result.scalar_one_or_none()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    job_result = await session.execute(select(Job).where(Job.id == bid.job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.owner_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    now = datetime.now(UTC).isoformat()
    bids_result = await session.execute(select(Bid).where(Bid.job_id == bid.job_id))
    for b in bids_result.scalars().all():
        b.status = "accepted" if b.id == quote_id else "rejected"
    job.supplier_user_id = bid.supplier_user_id
    job.accepted_bid_id = quote_id
    job.status = JobStatus.QUOTE_ACCEPTED
    job.updated_at = now
    if settings.hedera_is_real:
        supplier_result = await session.execute(select(User).where(User.id == bid.supplier_user_id))
        supplier = supplier_result.scalar_one()
        escrow_svc = EscrowService()
        escrow_id = escrow_svc.create_escrow_account_with_public_keys(
            supplier.hedera_public_key or ""
        )
        job.escrow_account_id = escrow_id
        logger.info(
            "escrow.account_created request_id=%s escrow_id=%s",
            bid.job_id, escrow_id,
        )
    await add_audit(session, bid.job_id, "quote_accepted", {"quote_id": quote_id})
    logger.info("quote.accepted request_id=%s quote_id=%s owner_wallet=%s amount=%s", bid.job_id, quote_id, user["hedera_account_id"], bid.amount_tinybar)
    return {
        "request_id": bid.job_id,
        "quote_id": quote_id,
        "status": JobStatus.QUOTE_ACCEPTED,
        "quote_amount": bid.amount_tinybar,
        "base_commitment_fee": base_fee_for(bid.amount_tinybar),
        "escrow_status": EscrowStatus.BASE_FEE_REQUIRED,
        "escrow_account_id": job.escrow_account_id,
    }


async def fund_escrow(
    session: AsyncSession,
    request_id: int,
    user: dict[str, Any],
    transaction_id: str | None = None,
) -> dict[str, Any]:
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.owner_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    if job.accepted_bid_id is None:
        raise HTTPException(status_code=409, detail="quote_not_accepted")
    bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
    bid = bid_result.scalar_one()
    now = datetime.now(UTC).isoformat()

    if settings.hedera_is_real:
        if not job.escrow_account_id:
            raise HTTPException(status_code=409, detail="escrow_not_created")
        if job.status == JobStatus.ESCROW_FUNDED:
            return {
                "request_id": request_id,
                "status": JobStatus.ESCROW_FUNDED,
                "escrow_status": EscrowStatus.ESCROW_FUNDED,
                "escrow_account_id": job.escrow_account_id,
            }
        escrow_svc = EscrowService()
        if transaction_id:
            # Mode 3: wallet already sent HBAR — poll to confirm balance arrived
            confirmed = await escrow_svc.poll_balance(job.escrow_account_id, bid.amount_tinybar, 30)
            if not confirmed:
                return {
                    "request_id": request_id,
                    "status": "funding_timeout",
                    "escrow_account_id": job.escrow_account_id,
                    "amount_tinybar": bid.amount_tinybar,
                }
            tx_id = transaction_id
        else:
            # Mode 2: server funds using DEV_OWNER_PRIVATE_KEY
            tx_id = escrow_svc.fund_from_dev_owner(job.escrow_account_id, bid.amount_tinybar)
        escrow = job.escrow_account_id
    else:
        escrow = f"0.0.{99000 + request_id}"
        tx_id = f"local:escrow:{request_id}"
        job.escrow_account_id = escrow

    job.status = JobStatus.ESCROW_FUNDED
    job.updated_at = now
    await record_transaction(session, request_id, "escrow_fund", bid.amount_tinybar, "HBAR", "settled", tx_id)
    await add_audit(session, request_id, "escrow_funded", {"amount": bid.amount_tinybar, "tx_id": tx_id})
    logger.info(
        "escrow.funded request_id=%s owner_wallet=%s amount=%s escrow=%s tx_id=%s",
        request_id, user["hedera_account_id"], bid.amount_tinybar, escrow, tx_id,
    )
    return {
        "request_id": request_id,
        "status": JobStatus.ESCROW_FUNDED,
        "escrow_status": EscrowStatus.ESCROW_FUNDED,
        "escrow_account_id": escrow,
        "hedera_tx_id": tx_id,
    }


async def record_transaction(session: AsyncSession, job_id: int, tx_type: str, amount: int, token: str, status: str, hedera_tx_id: str) -> None:
    tx = EscrowTransaction(
        job_id=job_id,
        type=tx_type,
        amount=amount,
        token=token,
        status=status,
        hedera_tx_id=hedera_tx_id,
        created_at=datetime.now(UTC).isoformat(),
    )
    session.add(tx)


async def run_ai_validation(session: AsyncSession, request_id: int) -> dict[str, Any]:
    photo_result = await session.execute(select(Photo).where(Photo.job_id == request_id))
    photos = photo_result.scalars().all()
    now = datetime.now(UTC).isoformat()
    if not photos:
        status_val = AIValidationStatus.NEEDS_MORE_EVIDENCE
        confidence = 0
    else:
        status_val = AIValidationStatus.PASSED
        confidence = 95
        photo_update_result = await session.execute(select(Photo).where(Photo.job_id == request_id))
        for p in photo_update_result.scalars().all():
            p.review_status = "passed"
            p.review_notes = "Validation passed by EscrowEye mock AI."
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one()
    job.status = JobStatus.AWAITING_OWNER_CONFIRMATION if photos else JobStatus.NEEDS_REVISION
    job.updated_at = now
    ai = AIValidation(
        job_id=request_id,
        status=status_val,
        confidence_score=confidence,
        issues_found="" if photos else "No proof uploaded",
        final_result=status_val,
        created_at=now,
    )
    session.add(ai)
    await add_audit(session, request_id, "ai_validation_completed", {"status": status_val})
    logger.info("ai.validation_completed request_id=%s status=%s confidence=%s", request_id, status_val, confidence)
    return {"request_id": request_id, "status": status_val, "confidence_score": confidence}


async def confirm_satisfaction(session: AsyncSession, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.owner_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    validation_result = await session.execute(select(AIValidation).where(AIValidation.job_id == request_id).order_by(AIValidation.id.desc()))
    validation = validation_result.scalar_one_or_none()
    if validation is None or validation.status != AIValidationStatus.PASSED:
        raise HTTPException(status_code=409, detail="validation_not_passed")
    job.status = JobStatus.COMPLETED
    await add_audit(session, request_id, "owner_confirmed")
    return {"request_id": request_id, "status": JobStatus.COMPLETED, "escrow_status": EscrowStatus.RELEASE_READY}


async def release_payment(session: AsyncSession, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.owner_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="owner_confirmation_required")
    bid = None
    if job.accepted_bid_id is not None:
        bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
        bid = bid_result.scalar_one_or_none()
    amount = bid.amount_tinybar if bid else job.suggested_price_tinybar
    if settings.hedera_is_real:
        if not job.escrow_account_id:
            raise HTTPException(status_code=409, detail="escrow_not_created")
        supplier_result = await session.execute(select(User).where(User.id == job.supplier_user_id))
        supplier = supplier_result.scalar_one()
        escrow_svc = EscrowService()
        tx_id = escrow_svc.release_escrow(job.escrow_account_id, supplier.hedera_account_id, amount)
    else:
        tx_id = f"local:release:{request_id}"
    await record_transaction(session, request_id, "release", amount, "HBAR", "settled", tx_id)
    await add_audit(session, request_id, "payment_released", {"tx_id": tx_id})
    logger.info("escrow.payment_released request_id=%s owner_wallet=%s amount=%s tx_id=%s", request_id, user["hedera_account_id"], amount, tx_id)
    return {"request_id": request_id, "status": JobStatus.COMPLETED, "escrow_status": EscrowStatus.RELEASED, "hedera_tx_id": tx_id}


async def supplier_jobs(session: AsyncSession, user: dict[str, Any], bucket: str) -> list[dict[str, Any]]:
    if bucket == "offers":
        result = await session.execute(select(Job).where(Job.status.in_([JobStatus.QUOTE_REQUESTED, JobStatus.QUOTE_RECEIVED])).order_by(Job.id.desc()))
    elif bucket == "active":
        result = await session.execute(
            select(Job).where(Job.supplier_user_id == user["id"], ~Job.status.in_([JobStatus.COMPLETED, JobStatus.DISPUTED])).order_by(Job.id.desc())
        )
    else:
        result = await session.execute(
            select(Job).where(Job.supplier_user_id == user["id"], Job.status.in_([JobStatus.COMPLETED, JobStatus.DISPUTED])).order_by(Job.id.desc())
        )
    rows = result.scalars().all()
    results = []
    for row in rows:
        results.append(await service_request_payload(session, row))
    return results


async def service_request_payload(session: AsyncSession, job: Job) -> dict[str, Any]:
    home_result = await session.execute(select(Home).where(Home.id == job.home_id))
    home = home_result.scalar_one_or_none()
    bid = None
    if job.accepted_bid_id is not None:
        bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
        bid = bid_result.scalar_one_or_none()
    owner = None
    if job.owner_user_id:
        owner_result = await session.execute(select(User).where(User.id == job.owner_user_id))
        owner = owner_result.scalar_one_or_none()
    supplier = None
    if job.supplier_user_id is not None:
        supplier_result = await session.execute(select(User).where(User.id == job.supplier_user_id))
        supplier = supplier_result.scalar_one_or_none()
    bids_result = await session.execute(select(func.count(Bid.id), func.min(Bid.amount_tinybar)).where(Bid.job_id == job.id, Bid.status != "withdrawn"))
    bids_row = bids_result.one()
    validation_result = await session.execute(select(AIValidation.status).where(AIValidation.job_id == job.id).order_by(AIValidation.id.desc()))
    validation = validation_result.scalar_one_or_none()
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "suggested_price_tinybar": job.suggested_price_tinybar,
        "home": {"id": home.id, "name": home.name, "address": home.address} if home else {"id": job.home_id, "name": "Service address", "address": ""},
        "owner": {"id": owner.id, "hedera_account_id": owner.hedera_account_id} if owner else None,
        "supplier": {"id": supplier.id, "hedera_account_id": supplier.hedera_account_id, "user_type": supplier.user_type} if supplier else None,
        "bid_count": bids_row[0] if bids_row else 0,
        "lowest_bid_tinybar": bids_row[1] if bids_row else None,
        "address": home.address if home else "",
        "schedule": job.available_times,
        "budget_amount": job.suggested_price_tinybar,
        "quote_amount": bid.amount_tinybar if bid else None,
        "base_commitment_fee": base_fee_for(bid.amount_tinybar) if bid else None,
        "status": job.status,
        "escrow_status": EscrowStatus.ESCROW_FUNDED if job.escrow_account_id else EscrowStatus.BASE_FEE_REQUIRED,
        "ai_validation_status": validation if validation else AIValidationStatus.WAITING_FOR_PROOF,
        "hcs_topic_id": job.hcs_topic_id,
        "escrow_account_id": job.escrow_account_id,
        "accepted_bid": {"id": bid.id, "amount_tinybar": bid.amount_tinybar} if bid else None,
        "access_notes": job.access_notes,
        "available_times": job.available_times,
        "creation_fee_paid": bool(job.creation_fee_paid),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
