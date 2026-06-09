from __future__ import annotations

import contextvars
import os
from typing import Any

import httpx
from langchain_core.tools import tool

API_BASE = os.getenv("AGENT_API_BASE", "http://localhost:8000")

_jwt_var: contextvars.ContextVar[str] = contextvars.ContextVar("agent_jwt", default="")


def set_agent_jwt(jwt: str) -> None:
    _jwt_var.set(jwt)


def get_agent_jwt() -> str:
    return _jwt_var.get()


async def _api_call(method: str, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
    jwt = get_agent_jwt()
    headers: dict[str, str] = {}
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    headers["X-Payment"] = "mock"
    async with httpx.AsyncClient(base_url=API_BASE) as client:
        resp = await client.request(method, path, json=json_data, headers=headers)
        resp.raise_for_status()
        return resp.json()


@tool
async def get_jobs(status: str | None = None) -> dict:
    """Get all jobs, optionally filtered by status.
    
    Status options: bidding, awarded, funded, in_progress, awaiting_confirmation, completed, disputed.
    """
    path = "/api/jobs"
    if status:
        path += f"?status={status}"
    return await _api_call("GET", path)


@tool
async def get_job(job_id: int) -> dict:
    """Get a single job by its ID."""
    return await _api_call("GET", f"/api/jobs/{job_id}")


@tool
async def create_job(
    home_id: int,
    title: str,
    description: str,
    suggested_price_tinybar: int,
    access_notes: str | None = None,
    available_times: str | None = None,
) -> dict:
    """Create a new cleaning job. Returns the created job or a 402 Payment Required response."""
    body: dict[str, Any] = {
        "home_id": home_id,
        "title": title,
        "description": description,
        "suggested_price_tinybar": suggested_price_tinybar,
    }
    if access_notes is not None:
        body["access_notes"] = access_notes
    if available_times is not None:
        body["available_times"] = available_times
    return await _api_call("POST", "/api/jobs", body)


@tool
async def get_homes() -> dict:
    """Get all homes for the current user."""
    return await _api_call("GET", "/api/homes")


@tool
async def create_home(name: str, address: str) -> dict:
    """Create a new home."""
    return await _api_call("POST", "/api/homes", {"name": name, "address": address})


@tool
async def place_bid(job_id: int, amount_tinybar: int, message: str = "") -> dict:
    """Place a bid on a job. Amount is in tinybars (1 HBAR = 100,000,000 tinybars)."""
    body: dict[str, Any] = {"amount_tinybar": amount_tinybar}
    if message:
        body["message"] = message
    return await _api_call("POST", f"/api/jobs/{job_id}/bids", body)


@tool
async def get_bids(job_id: int) -> dict:
    """Get all bids for a job."""
    return await _api_call("GET", f"/api/jobs/{job_id}/bids")


@tool
async def award_bid(job_id: int, bid_id: int) -> dict:
    """Award a bid (accept it) for a job. Sets the supplier and moves job to awarded status."""
    return await _api_call("POST", f"/api/jobs/{job_id}/award", {"bid_id": bid_id})


@tool
async def fund_escrow(job_id: int, transaction_id: str = "") -> dict:
    """Fund the escrow account for a job.
    In dev mode, this simulates funding instantly.
    In testnet mode, the first call returns awaiting_funding with the escrow account ID.
    The user sends HBAR from their wallet, then calls this tool again with the transaction_id
    to confirm the funds arrived. The server polls the network until confirmed."""
    body = {}
    if transaction_id:
        body["transaction_id"] = transaction_id
    return await _api_call("POST", f"/api/jobs/{job_id}/fund", body if body else None)


@tool
async def mark_ready(job_id: int, message: str = "") -> dict:
    """Mark a job as ready for review (supplier indicates work is done)."""
    body: dict[str, Any] = {}
    if message:
        body["message"] = message
    return await _api_call("POST", f"/api/jobs/{job_id}/mark-ready", body)


@tool
async def send_message(job_id: int, body: str, photo_ids: list[int] | None = None) -> dict:
    """Send a message on a job conversation thread. Optionally attach photo IDs."""
    payload: dict[str, Any] = {"body": body}
    if photo_ids:
        payload["photo_ids"] = photo_ids
    return await _api_call("POST", f"/api/jobs/{job_id}/messages", payload)


@tool
async def get_messages(job_id: int) -> dict:
    """Get all messages for a job conversation."""
    return await _api_call("GET", f"/api/jobs/{job_id}/messages")


@tool
async def get_photos(job_id: int) -> dict:
    """Get all photos for a job."""
    return await _api_call("GET", f"/api/jobs/{job_id}/photos")


@tool
async def associate_photo(
    job_id: int,
    photo_id: int,
    room_id: int,
    review_status: str,
    review_notes: str | None = None,
) -> dict:
    """Associate a photo with a room and set its review status.
    review_status options: pending, passed, failed, needs_retake.
    """
    body: dict[str, Any] = {
        "room_id": room_id,
        "review_status": review_status,
    }
    if review_notes is not None:
        body["review_notes"] = review_notes
    return await _api_call("PATCH", f"/api/jobs/{job_id}/photos/{photo_id}", body)


@tool
async def check_funding(job_id: int) -> dict:
    """Check if a job's escrow has been funded yet. Returns current status."""
    return await _api_call("GET", f"/api/jobs/{job_id}")


@tool
async def confirm_job(job_id: int) -> dict:
    """Confirm a job is complete. Owner marks satisfaction."""
    return await _api_call("POST", f"/api/jobs/{job_id}/confirm")


@tool
async def dispute_job(job_id: int, reason: str) -> dict:
    """Dispute a job. Provide the reason for the dispute."""
    return await _api_call("POST", f"/api/jobs/{job_id}/dispute", {"reason": reason})
