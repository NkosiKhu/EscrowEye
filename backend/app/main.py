from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.ai_validation import create_ai_validation_router
from app.api.routes.audit import create_audit_router
from app.api.routes.auth import create_auth_router
from app.api.routes.earnings import create_earnings_router
from app.api.routes.escrow import create_escrow_router
from app.api.routes.homes import create_homes_router
from app.api.routes.jobs import create_jobs_router
from app.api.routes.proof import create_proof_router
from app.api.routes.quotes import create_quotes_router
from app.api.routes.service_requests import create_service_requests_router
from app.api.routes.workers import router as workers_router
from app.api.routes.x402 import router as x402_router
from app.core.logging import (
    configure_logging,
    get_logger,
    set_request_context,
)
from app.infrastructure.database import (
    close_engine,
    create_tables,
    get_session,
)
from app.infrastructure.models import User
from app.infrastructure.x402_service import X402Service
from app.services import marketplace as marketplace_service


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploads"

configure_logging()
logger = get_logger("escroweye.main")

SECRET = os.getenv("ESCROWEYE_SECRET", "escroweye-dev-secret").encode()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
x402_service = X402Service()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await load_local_creds()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    await create_tables()
    async with get_session() as session:
        await seed_service_categories(session)
    logger.info("app.startup db_engine=async_sqlalchemy upload_dir=%s", UPLOAD_DIR)
    yield
    await close_engine()
    logger.info("app.shutdown")


app = FastAPI(title="EscrowEye API", version="0.1.0", lifespan=lifespan)


async def load_local_creds() -> None:
    creds_path = PROJECT_DIR / "creds"
    if not creds_path.exists() or not creds_path.is_file():
        return
    for raw_line in creds_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.perf_counter()
        set_request_context(request_id=request_id, path=request.url.path)
        logger.info("request.start method=%s path=%s", request.method, request.url.path)
        try:
            response = await call_next(request)
        except HTTPException:
            raise
        except Exception:
            logger.exception("request.error method=%s path=%s", request.method, request.url.path)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request.finish method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(workers_router)
app.include_router(x402_router)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def token_for(user_id: int) -> str:
    ts = str(int(time.time()))
    payload = f"{user_id}.{ts}.{secrets.token_hex(8)}"
    sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token: str) -> int:
    parts = token.split(".")
    if len(parts) != 4:
        raise HTTPException(status_code=401, detail="invalid_token")
    payload = ".".join(parts[:3])
    expected = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[3]):
        raise HTTPException(status_code=401, detail="invalid_token")
    return int(parts[0])


async def current_user_dep(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    user_id = verify_token(authorization.removeprefix("Bearer ").strip())
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="user_not_found")
    user_dict = {
        "id": user.id,
        "email": user.email,
        "user_type": user.user_type,
        "hedera_account_id": user.hedera_account_id,
        "hedera_public_key": user.hedera_public_key or "",
    }
    set_request_context(request_id="-", user_id=str(user.id), path="-")
    logger.debug("auth.current_user user_id=%s wallet=%s role=%s", user.id, user.hedera_account_id, user.user_type)
    return user_dict


def public_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user["id"],
        "email": user.get("email"),
        "user_type": user.get("user_type"),
        "hedera_account_id": user.get("hedera_account_id"),
        "hedera_public_key": user.get("hedera_public_key"),
    }


def room_payload(room: dict[str, Any] | None) -> dict[str, Any] | None:
    if room is None:
        return None
    return {"id": room["id"], "name": room["name"], "sq_meters": room.get("sq_meters")}


async def seed_service_categories(session: AsyncSession) -> None:
    from app.infrastructure.models import ServiceCategory

    for cat in marketplace_service.SERVICE_CATEGORIES:
        existing = await session.execute(
            select(ServiceCategory).where(ServiceCategory.id == cat["id"])
        )
        if existing.scalar_one_or_none() is None:
            session.add(ServiceCategory(**cat))
    await session.commit()


async def add_audit_async(session: AsyncSession, job_id: int, event_type: str, tx_hash: str | None = None) -> None:
    from app.infrastructure.hcs_service import HCSService
    from app.infrastructure.models import AuditEvent

    result = await session.execute(
        select(func.coalesce(func.max(AuditEvent.sequence_number), 0) + 1).where(AuditEvent.job_id == job_id)
    )
    seq = result.scalar()
    hcs_result = HCSService().submit_event(event_type, {"job_id": job_id})
    audit = AuditEvent(
        job_id=job_id,
        type=event_type,
        tx_hash=tx_hash or hcs_result.tx_id,
        sequence_number=seq,
        consensus_timestamp=now_iso(),
        hcs_status=hcs_result.status,
        payload_json="{}",
    )
    session.add(audit)





@app.get("/")
async def root():
    return {"app": "EscrowEye", "status": "ok", "version": "0.1.0"}


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "healthy"}


app.include_router(
    create_homes_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
        room_payload=room_payload,
    )
)

app.include_router(
    create_auth_router(
        db=get_session,
        now_iso=now_iso,
        token_for=token_for,
        current_user=current_user_dep,
        public_user=public_user,
    )
)

app.include_router(
    create_jobs_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
        public_user=public_user,
        add_audit=add_audit_async,
        base_dir=BASE_DIR,
        upload_dir=UPLOAD_DIR,
        openrouter_api_key=OPENROUTER_API_KEY,
        openrouter_model=OPENROUTER_MODEL,
        x402_service=x402_service,
    )
)

app.include_router(
    create_service_requests_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
        public_user=public_user,
        x402_service=x402_service,
    )
)

app.include_router(
    create_quotes_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
    )
)

app.include_router(
    create_escrow_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
    )
)

app.include_router(
    create_proof_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
        upload_dir=UPLOAD_DIR,
    )
)

app.include_router(
    create_ai_validation_router(
        db=get_session,
        now_iso=now_iso,
        current_user=current_user_dep,
    )
)

app.include_router(
    create_earnings_router(
        db=get_session,
        current_user=current_user_dep,
    )
)

app.include_router(
    create_audit_router(
        db=get_session,
        current_user=current_user_dep,
    )
)
