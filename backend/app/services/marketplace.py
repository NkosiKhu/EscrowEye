from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from fastapi import HTTPException

from app.core.logging import get_logger
from app.domain.enums import AIValidationStatus, EscrowStatus, JobStatus
from app.infrastructure.hcs_service import HCSService


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
        "average_rate": "From ₦80k",
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
        "average_rate": "From ₦120k",
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
        "average_rate": "From ₦65k",
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
    return next((category for category in SERVICE_CATEGORIES if category["slug"] == slug or category["name"].lower() == slug.lower()), None)


def list_workers(category: str | None = None, location: str | None = None) -> list[dict[str, Any]]:
    workers = WORKERS
    if category:
        slug = (category_by_slug(category) or {"slug": category})["slug"]
        workers = [worker for worker in workers if slug in worker["services"]]
    if location:
        needle = location.lower()
        workers = [worker for worker in workers if needle in worker["location"].lower()]
    return workers


def set_user_role(conn: sqlite3.Connection, user: dict[str, Any], role: str) -> dict[str, str]:
    if role not in {"owner", "supplier"}:
        raise HTTPException(status_code=422, detail="invalid_role")
    conn.execute("UPDATE users SET user_type = ? WHERE id = ?", (role, user["id"]))
    logger.info("user.role_updated user_id=%s wallet=%s role=%s", user["id"], user["hedera_account_id"], role)
    return {"role": role}


def setup_profile(conn: sqlite3.Connection, body: Any, user: dict[str, Any], public_user: Any) -> dict[str, Any]:
    conn.execute(
        """
        UPDATE users
        SET first_name = ?, last_name = ?, profile_photo_url = ?, location = ?,
            service_area = ?, payment_token_preference = ?
        WHERE id = ?
        """,
        (
            body.first_name,
            body.last_name,
            body.profile_photo_url,
            body.location,
            body.service_area,
            body.payment_token_preference,
            user["id"],
        ),
    )
    if user["user_type"] == "supplier":
        conn.execute(
            """
            INSERT INTO supplier_profiles (
                user_id, services_offered, work_experience, portfolio_items, average_rate,
                rating, reviews_count, verification_status, created_at, updated_at
            ) VALUES (?, 'Cleaning, Maintenance', '3 years', '[]', 'From ₦80k', 4.8, 0, 'verified', datetime('now'), datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (user["id"],),
        )
    updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    payload = public_user(updated)
    payload.update(body.model_dump())
    return payload


def list_service_requests(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    if user["user_type"] == "owner":
        rows = conn.execute("SELECT * FROM jobs WHERE owner_user_id = ? ORDER BY id DESC", (user["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs WHERE supplier_user_id = ? OR status IN ('quote_requested', 'quote_received') ORDER BY id DESC", (user["id"],)).fetchall()
    return {"requests": [service_request_payload(conn, row) for row in rows]}


def get_service_request(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return service_request_payload(conn, row)


def update_service_request(conn: sqlite3.Connection, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (request_id, user["id"])).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute(
        "UPDATE jobs SET title = ?, description = ?, suggested_price_tinybar = ?, access_notes = ?, available_times = ?, updated_at = datetime('now') WHERE id = ?",
        (body.title, body.description, body.budget_amount, body.location_description, body.schedule, request_id),
    )
    add_local_audit(conn, request_id, "service_request_updated")
    return get_service_request(conn, request_id)


def cancel_service_request(conn: sqlite3.Connection, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (request_id, user["id"])).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET status = 'cancelled', updated_at = datetime('now') WHERE id = ?", (request_id,))
    add_local_audit(conn, request_id, "service_request_cancelled")
    return {"request_id": request_id, "status": "cancelled"}


def supplier_accept_job(conn: sqlite3.Connection, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET supplier_user_id = ?, status = 'accepted', updated_at = datetime('now') WHERE id = ?", (user["id"], job_id))
    add_local_audit(conn, job_id, "supplier_accepted")
    return {"job_id": job_id, "status": "accepted"}


def supplier_mark_processing(conn: sqlite3.Connection, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    if conn.execute("SELECT id FROM jobs WHERE id = ? AND supplier_user_id = ?", (job_id, user["id"])).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET status = 'processing', updated_at = datetime('now') WHERE id = ?", (job_id,))
    add_local_audit(conn, job_id, "supplier_processing")
    return {"job_id": job_id, "status": "processing"}


def supplier_mark_complete(conn: sqlite3.Connection, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    if conn.execute("SELECT id FROM jobs WHERE id = ? AND supplier_user_id = ?", (job_id, user["id"])).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET status = 'awaiting_owner_confirmation', updated_at = datetime('now') WHERE id = ?", (job_id,))
    add_local_audit(conn, job_id, "supplier_marked_complete")
    return {"job_id": job_id, "status": "awaiting_owner_confirmation"}


def message_payload(conn: sqlite3.Connection, msg: sqlite3.Row) -> dict[str, Any]:
    sender = conn.execute("SELECT * FROM users WHERE id = ?", (msg["sender_user_id"],)).fetchone() if msg["sender_user_id"] else None
    return {
        "id": msg["id"],
        "sender_user_id": msg["sender_user_id"],
        "sender": dict(sender) if sender else None,
        "sender_type": msg["sender_type"],
        "body": msg["body"],
        "photo_ids": [],
        "photos": [],
        "created_at": msg["created_at"],
    }


def list_service_messages(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (request_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    messages = conn.execute("SELECT * FROM messages WHERE job_id = ? ORDER BY id", (request_id,)).fetchall()
    return {"messages": [message_payload(conn, msg) for msg in messages]}


def create_service_message(conn: sqlite3.Connection, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (request_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    cur = conn.execute(
        "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (request_id, user["id"], body.type, body.body),
    )
    return message_payload(conn, conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone())


def list_request_quotes(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM bids WHERE job_id = ? AND status != 'withdrawn' ORDER BY amount_tinybar", (request_id,)).fetchall()
    return {"quotes": [quote_payload(conn, row) for row in rows]}


def reject_quote(conn: sqlite3.Connection, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (quote_id,)).fetchone()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    if conn.execute("SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (bid["job_id"], user["id"])).fetchone() is None:
        raise HTTPException(status_code=403, detail="owner_role_required")
    conn.execute("UPDATE bids SET status = 'rejected', updated_at = datetime('now') WHERE id = ?", (quote_id,))
    add_local_audit(conn, bid["job_id"], "quote_rejected")
    return {"quote_id": quote_id, "status": "rejected"}


def withdraw_quote(conn: sqlite3.Connection, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid = conn.execute("SELECT * FROM bids WHERE id = ? AND supplier_user_id = ?", (quote_id, user["id"])).fetchone()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE bids SET status = 'withdrawn', updated_at = datetime('now') WHERE id = ?", (quote_id,))
    add_local_audit(conn, bid["job_id"], "quote_withdrawn")
    return {"quote_id": quote_id, "status": "withdrawn"}


def pay_base_fee(conn: sqlite3.Connection, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE id = ? AND owner_user_id = ?", (request_id, user["id"])).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if not job["accepted_bid_id"]:
        raise HTTPException(status_code=409, detail="quote_not_accepted")
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone()
    fee = base_fee_for(bid["amount_tinybar"])
    record_transaction(conn, request_id, "base_fee", fee, "HBAR", "settled", f"local:base-fee:{request_id}")
    add_local_audit(conn, request_id, "base_fee_paid", {"amount": fee})
    logger.info("escrow.base_fee_paid request_id=%s owner_wallet=%s amount=%s", request_id, user["hedera_account_id"], fee)
    return {"request_id": request_id, "status": "base_fee_paid", "amount": fee}


def service_escrow(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone() if job["accepted_bid_id"] else None
    return {
        "request_id": request_id,
        "escrow_account_id": job["escrow_account_id"],
        "quote_amount": bid["amount_tinybar"] if bid else None,
        "base_commitment_fee": base_fee_for(bid["amount_tinybar"]) if bid else None,
        "escrow_status": "escrow_funded" if job["escrow_account_id"] else "escrow_pending",
    }


def dispute_service_request(conn: sqlite3.Connection, request_id: int, reason: str, user: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (request_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET status = 'disputed', updated_at = datetime('now') WHERE id = ?", (request_id,))
    add_local_audit(conn, request_id, "dispute_opened", {"reason": reason, "user_id": user["id"]})
    return {"request_id": request_id, "status": "disputed"}


def get_ai_validation(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM ai_validations WHERE job_id = ? ORDER BY id DESC", (request_id,)).fetchone()
    if row is None:
        return {"request_id": request_id, "status": "waiting_for_proof", "confidence_score": 0}
    return dict(row)


def request_ai_corrections(conn: sqlite3.Connection, request_id: int, body: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (request_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    conn.execute("UPDATE jobs SET status = 'needs_revision', updated_at = datetime('now') WHERE id = ?", (request_id,))
    add_local_audit(conn, request_id, "ai_requested_corrections", body)
    return {"request_id": request_id, "status": "needs_more_evidence"}


def audit_events(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    job = conn.execute("SELECT hcs_topic_id FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    rows = conn.execute(
        "SELECT type, job_id, tx_hash, sequence_number, consensus_timestamp FROM audit_events WHERE job_id = ? ORDER BY sequence_number",
        (request_id,),
    ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        if item["tx_hash"] is None:
            item.pop("tx_hash")
        events.append(item)
    return {"hcs_topic_id": job["hcs_topic_id"], "events": events}


def hcs_topic(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    job = conn.execute("SELECT hcs_topic_id FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    return {"request_id": request_id, "hcs_topic_id": job["hcs_topic_id"]}


def create_audit_event(conn: sqlite3.Connection, request_id: int, body: dict[str, Any]) -> dict[str, Any]:
    if conn.execute("SELECT id FROM jobs WHERE id = ?", (request_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="not_found")
    add_local_audit(conn, request_id, str(body.get("event_type", "custom_event")), body)
    return {"request_id": request_id, "status": "recorded"}


def supplier_earnings(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    accepted = conn.execute(
        """
        SELECT COALESCE(SUM(b.amount_tinybar), 0) total
        FROM bids b JOIN jobs j ON j.accepted_bid_id = b.id
        WHERE b.supplier_user_id = ? AND j.status != 'completed'
        """,
        (user["id"],),
    ).fetchone()["total"]
    paid = conn.execute(
        """
        SELECT COALESCE(SUM(t.amount), 0) total
        FROM escrow_transactions t JOIN jobs j ON j.id = t.job_id
        WHERE j.supplier_user_id = ? AND t.type = 'release'
        """,
        (user["id"],),
    ).fetchone()["total"]
    return {"pending_earnings": accepted, "past_earnings": paid, "total_earnings": accepted + paid}


def supplier_transactions(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    rows = conn.execute(
        """
        SELECT t.* FROM escrow_transactions t JOIN jobs j ON j.id = t.job_id
        WHERE j.supplier_user_id = ? ORDER BY t.id DESC
        """,
        (user["id"],),
    ).fetchall()
    return {"transactions": [dict(row) for row in rows]}


def owner_payments(conn: sqlite3.Connection, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "owner")
    rows = conn.execute("SELECT t.* FROM escrow_transactions t JOIN jobs j ON j.id = t.job_id WHERE j.owner_user_id = ? ORDER BY t.id DESC", (user["id"],)).fetchall()
    return {"payments": [dict(row) for row in rows]}


def add_local_audit(conn: sqlite3.Connection, job_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
    event_payload = payload or {}
    job = conn.execute("SELECT hcs_topic_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    hcs_result = HCSService().submit_event(event_type, {"job_id": job_id, **event_payload}, job["hcs_topic_id"] if job else None)
    seq = conn.execute("SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM audit_events WHERE job_id = ?", (job_id,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO audit_events (job_id, type, tx_hash, sequence_number, consensus_timestamp, hcs_status, payload_json)
        VALUES (?, ?, ?, ?, datetime('now'), ?, ?)
        """,
        (job_id, event_type, hcs_result.tx_id, seq, hcs_result.status, str(event_payload)),
    )
    logger.info("audit.recorded job_id=%s event=%s hcs_status=%s tx_id=%s", job_id, event_type, hcs_result.status, hcs_result.tx_id)


def create_request(conn: sqlite3.Connection, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "owner")
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    home_cur = conn.execute(
        "INSERT INTO homes (owner_user_id, name, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], body.title[:48], body.address, now, now),
    )
    hcs_topic = f"0.0.{88880 + home_cur.lastrowid}"
    job_cur = conn.execute(
        """
        INSERT INTO jobs (
            home_id, owner_user_id, title, description, suggested_price_tinybar, access_notes,
            available_times, status, hcs_topic_id, creation_fee_paid, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            home_cur.lastrowid,
            user["id"],
            body.title,
            body.description,
            body.budget_amount,
            body.location_description,
            body.schedule,
            JobStatus.QUOTE_REQUESTED,
            hcs_topic,
            now,
            now,
        ),
    )
    add_local_audit(conn, job_cur.lastrowid, "service_request_created", {"category": body.category})
    logger.info("service_request.created request_id=%s owner_wallet=%s category=%s budget=%s", job_cur.lastrowid, user["hedera_account_id"], body.category, body.budget_amount)
    return {"id": job_cur.lastrowid, "status": JobStatus.QUOTE_REQUESTED, "hcs_topic_id": hcs_topic}


def quote_payload(conn: sqlite3.Connection, bid: sqlite3.Row) -> dict[str, Any]:
    supplier = conn.execute("SELECT * FROM users WHERE id = ?", (bid["supplier_user_id"],)).fetchone()
    return {
        "id": bid["id"],
        "request_id": bid["job_id"],
        "supplier_id": bid["supplier_user_id"],
        "supplier": {"id": supplier["id"], "hedera_account_id": supplier["hedera_account_id"]} if supplier else None,
        "amount": bid["amount_tinybar"],
        "amount_tinybar": bid["amount_tinybar"],
        "message": bid["message"],
        "status": bid["status"],
        "created_at": bid["created_at"],
    }


def create_quote(conn: sqlite3.Connection, request_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
    require_role(user, "supplier")
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, message, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (request_id, user["id"], body.amount, body.message, now, now),
    )
    conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (JobStatus.QUOTE_RECEIVED, now, request_id))
    add_local_audit(conn, request_id, "quote_submitted", {"amount": body.amount})
    logger.info("quote.created request_id=%s quote_id=%s supplier_wallet=%s amount=%s", request_id, cur.lastrowid, user["hedera_account_id"], body.amount)
    return quote_payload(conn, conn.execute("SELECT * FROM bids WHERE id = ?", (cur.lastrowid,)).fetchone())


def accept_quote(conn: sqlite3.Connection, quote_id: int, user: dict[str, Any]) -> dict[str, Any]:
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (quote_id,)).fetchone()
    if bid is None:
        raise HTTPException(status_code=404, detail="not_found")
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (bid["job_id"],)).fetchone()
    if job["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    conn.execute("UPDATE bids SET status = CASE WHEN id = ? THEN 'accepted' ELSE 'rejected' END WHERE job_id = ?", (quote_id, bid["job_id"]))
    conn.execute(
        "UPDATE jobs SET supplier_user_id = ?, accepted_bid_id = ?, status = ?, updated_at = ? WHERE id = ?",
        (bid["supplier_user_id"], quote_id, JobStatus.QUOTE_ACCEPTED, now, bid["job_id"]),
    )
    add_local_audit(conn, bid["job_id"], "quote_accepted", {"quote_id": quote_id})
    logger.info("quote.accepted request_id=%s quote_id=%s owner_wallet=%s amount=%s", bid["job_id"], quote_id, user["hedera_account_id"], bid["amount_tinybar"])
    return {
        "request_id": bid["job_id"],
        "quote_id": quote_id,
        "status": JobStatus.QUOTE_ACCEPTED,
        "quote_amount": bid["amount_tinybar"],
        "base_commitment_fee": base_fee_for(bid["amount_tinybar"]),
        "escrow_status": EscrowStatus.BASE_FEE_REQUIRED,
    }


def fund_escrow(conn: sqlite3.Connection, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    if not job["accepted_bid_id"]:
        raise HTTPException(status_code=409, detail="quote_not_accepted")
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone()
    escrow = f"0.0.{99000 + request_id}"
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    conn.execute("UPDATE jobs SET status = ?, escrow_account_id = ?, updated_at = ? WHERE id = ?", (JobStatus.ESCROW_FUNDED, escrow, now, request_id))
    record_transaction(conn, request_id, "escrow_fund", bid["amount_tinybar"], "HBAR", "settled", f"local:escrow:{request_id}")
    add_local_audit(conn, request_id, "escrow_funded", {"amount": bid["amount_tinybar"]})
    logger.info("escrow.funded request_id=%s owner_wallet=%s amount=%s escrow=%s", request_id, user["hedera_account_id"], bid["amount_tinybar"], escrow)
    return {"request_id": request_id, "status": JobStatus.ESCROW_FUNDED, "escrow_status": EscrowStatus.ESCROW_FUNDED, "escrow_account_id": escrow}


def record_transaction(conn: sqlite3.Connection, job_id: int, tx_type: str, amount: int, token: str, status: str, hedera_tx_id: str) -> None:
    conn.execute(
        """
        INSERT INTO escrow_transactions (job_id, type, amount, token, status, hedera_tx_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (job_id, tx_type, amount, token, status, hedera_tx_id),
    )


def mock_cid(content: bytes, filename: str) -> str:
    digest = hashlib.sha256(filename.encode() + b":" + content).hexdigest()
    return "bafy" + digest[:45]


def run_ai_validation(conn: sqlite3.Connection, request_id: int) -> dict[str, Any]:
    photos = conn.execute("SELECT * FROM photos WHERE job_id = ?", (request_id,)).fetchall()
    if not photos:
        status = AIValidationStatus.NEEDS_MORE_EVIDENCE
        confidence = 0
    else:
        status = AIValidationStatus.PASSED
        confidence = 95
        conn.execute("UPDATE photos SET review_status = 'passed', review_notes = 'Validation passed by EscrowEye mock AI.' WHERE job_id = ?", (request_id,))
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (JobStatus.AWAITING_OWNER_CONFIRMATION if photos else JobStatus.NEEDS_REVISION, now, request_id))
    conn.execute(
        """
        INSERT INTO ai_validations (job_id, status, confidence_score, issues_found, final_result, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (request_id, status, confidence, "" if photos else "No proof uploaded", status, now),
    )
    add_local_audit(conn, request_id, "ai_validation_completed", {"status": status})
    logger.info("ai.validation_completed request_id=%s status=%s confidence=%s", request_id, status, confidence)
    return {"request_id": request_id, "status": status, "confidence_score": confidence}


def confirm_satisfaction(conn: sqlite3.Connection, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    validation = conn.execute("SELECT * FROM ai_validations WHERE job_id = ? ORDER BY id DESC", (request_id,)).fetchone()
    if validation is None or validation["status"] != AIValidationStatus.PASSED:
        raise HTTPException(status_code=409, detail="validation_not_passed")
    conn.execute("UPDATE jobs SET status = ?, updated_at = datetime('now') WHERE id = ?", (JobStatus.COMPLETED, request_id))
    add_local_audit(conn, request_id, "owner_confirmed")
    return {"request_id": request_id, "status": JobStatus.COMPLETED, "escrow_status": EscrowStatus.RELEASE_READY}


def release_payment(conn: sqlite3.Connection, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (request_id,)).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job["owner_user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="owner_confirmation_required")
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone()
    amount = bid["amount_tinybar"] if bid else job["suggested_price_tinybar"]
    tx_id = f"local:release:{request_id}"
    record_transaction(conn, request_id, "release", amount, "HBAR", "settled", tx_id)
    add_local_audit(conn, request_id, "payment_released", {"tx_id": tx_id})
    logger.info("escrow.payment_released request_id=%s owner_wallet=%s amount=%s tx_id=%s", request_id, user["hedera_account_id"], amount, tx_id)
    return {"request_id": request_id, "status": JobStatus.COMPLETED, "escrow_status": EscrowStatus.RELEASED, "hedera_tx_id": tx_id}


def supplier_jobs(conn: sqlite3.Connection, user: dict[str, Any], bucket: str) -> list[dict[str, Any]]:
    if bucket == "offers":
        rows = conn.execute("SELECT * FROM jobs WHERE status IN (?, ?) ORDER BY id DESC", (JobStatus.QUOTE_REQUESTED, JobStatus.QUOTE_RECEIVED)).fetchall()
    elif bucket == "active":
        rows = conn.execute("SELECT * FROM jobs WHERE supplier_user_id = ? AND status NOT IN (?, ?) ORDER BY id DESC", (user["id"], JobStatus.COMPLETED, JobStatus.DISPUTED)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs WHERE supplier_user_id = ? AND status IN (?, ?) ORDER BY id DESC", (user["id"], JobStatus.COMPLETED, JobStatus.DISPUTED)).fetchall()
    return [service_request_payload(conn, row) for row in rows]


def service_request_payload(conn: sqlite3.Connection, job: sqlite3.Row) -> dict[str, Any]:
    home = conn.execute("SELECT id, name, address FROM homes WHERE id = ?", (job["home_id"],)).fetchone()
    bid = conn.execute("SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone() if job["accepted_bid_id"] else None
    owner = conn.execute("SELECT * FROM users WHERE id = ?", (job["owner_user_id"],)).fetchone()
    supplier = conn.execute("SELECT * FROM users WHERE id = ?", (job["supplier_user_id"],)).fetchone() if job["supplier_user_id"] else None
    bids = conn.execute("SELECT COUNT(*) c, MIN(amount_tinybar) m FROM bids WHERE job_id = ? AND status != 'withdrawn'", (job["id"],)).fetchone()
    validation = conn.execute("SELECT status FROM ai_validations WHERE job_id = ? ORDER BY id DESC", (job["id"],)).fetchone()
    return {
        "id": job["id"],
        "title": job["title"],
        "description": job["description"],
        "suggested_price_tinybar": job["suggested_price_tinybar"],
        "home": dict(home) if home else {"id": job["home_id"], "name": "Service address", "address": ""},
        "owner": {"id": owner["id"], "hedera_account_id": owner["hedera_account_id"]} if owner else None,
        "supplier": {"id": supplier["id"], "hedera_account_id": supplier["hedera_account_id"], "user_type": supplier["user_type"]} if supplier else None,
        "bid_count": bids["c"],
        "lowest_bid_tinybar": bids["m"],
        "address": home["address"] if home else "",
        "schedule": job["available_times"],
        "budget_amount": job["suggested_price_tinybar"],
        "quote_amount": bid["amount_tinybar"] if bid else None,
        "base_commitment_fee": base_fee_for(bid["amount_tinybar"]) if bid else None,
        "status": job["status"],
        "escrow_status": EscrowStatus.ESCROW_FUNDED if job["escrow_account_id"] else EscrowStatus.BASE_FEE_REQUIRED,
        "ai_validation_status": validation["status"] if validation else AIValidationStatus.WAITING_FOR_PROOF,
        "hcs_topic_id": job["hcs_topic_id"],
        "escrow_account_id": job["escrow_account_id"],
        "accepted_bid": {"id": bid["id"], "amount_tinybar": bid["amount_tinybar"]} if bid else None,
        "access_notes": job["access_notes"],
        "available_times": job["available_times"],
        "creation_fee_paid": bool(job["creation_fee_paid"]),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }
