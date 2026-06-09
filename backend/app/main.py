from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

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
from app.core.logging import configure_logging, get_logger
from app.infrastructure.x402_service import X402Service
from app.services import marketplace as marketplace_service


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "escroweye.sqlite3"
UPLOAD_DIR = BASE_DIR / "uploads"


def load_local_creds() -> None:
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


load_local_creds()
configure_logging()
logger = get_logger("escroweye.main")
SECRET = os.getenv("ESCROWEYE_SECRET", "escroweye-dev-secret").encode()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")
x402_service = X402Service()

app = FastAPI(title="EscrowEye API", version="0.1.0")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.perf_counter()
        logger.info("request.start id=%s method=%s path=%s", request_id, request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request.error id=%s method=%s path=%s", request_id, request.method, request.url.path)
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request.finish id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
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


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def one(conn: sqlite3.Connection, query: str, args: tuple[Any, ...] = ()) -> sqlite3.Row:
    row = conn.execute(query, args).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return row


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


def current_user(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    user_id = verify_token(authorization.removeprefix("Bearer ").strip())
    with db() as conn:
        user = dict(one(conn, "SELECT * FROM users WHERE id = ?", (user_id,)))
        logger.debug("auth.current_user user_id=%s wallet=%s role=%s", user["id"], user["hedera_account_id"], user["user_type"])
        return user


def public_user(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    return {
        "id": data["id"],
        "email": data.get("email"),
        "user_type": data.get("user_type"),
        "hedera_account_id": data.get("hedera_account_id"),
        "hedera_public_key": data.get("hedera_public_key"),
    }


app.include_router(
    create_auth_router(
        db=db,
        one=one,
        now_iso=now_iso,
        token_for=token_for,
        current_user=current_user,
        public_user=public_user,
    )
)


def room_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "sq_meters": row["sq_meters"]}


def add_audit(conn: sqlite3.Connection, job_id: int, event_type: str, tx_hash: str | None = None) -> None:
    seq = conn.execute("SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM audit_events WHERE job_id = ?", (job_id,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO audit_events (job_id, type, tx_hash, sequence_number, consensus_timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, event_type, tx_hash, seq, now_iso().replace("Z", ".000000000Z")),
    )


def init_db() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                user_type TEXT NOT NULL,
                hedera_account_id TEXT NOT NULL UNIQUE,
                hedera_public_key TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS challenges (
                nonce TEXT PRIMARY KEY,
                hedera_account_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS homes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_id INTEGER NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                sq_meters REAL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                home_id INTEGER NOT NULL REFERENCES homes(id) ON DELETE CASCADE,
                owner_user_id INTEGER NOT NULL REFERENCES users(id),
                supplier_user_id INTEGER REFERENCES users(id),
                accepted_bid_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                suggested_price_tinybar INTEGER NOT NULL,
                access_notes TEXT,
                available_times TEXT,
                status TEXT NOT NULL,
                escrow_account_id TEXT,
                hcs_topic_id TEXT NOT NULL,
                creation_fee_paid INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bids (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                supplier_user_id INTEGER NOT NULL REFERENCES users(id),
                amount_tinybar INTEGER NOT NULL,
                message TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                sender_user_id INTEGER REFERENCES users(id),
                sender_type TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS message_photos (
                message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
                PRIMARY KEY (message_id, photo_id)
            );
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
                uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
                cid TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT,
                storage_path TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                review_status TEXT NOT NULL,
                review_notes TEXT,
                encrypted_keys TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                tx_hash TEXT,
                sequence_number INTEGER NOT NULL,
                consensus_timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                confidence_score INTEGER NOT NULL,
                issues_found TEXT,
                requested_corrections TEXT,
                final_result TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS escrow_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                token TEXT NOT NULL,
                status TEXT NOT NULL,
                hedera_tx_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS supplier_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                services_offered TEXT,
                work_experience TEXT,
                portfolio_items TEXT,
                average_rate TEXT,
                rating REAL NOT NULL DEFAULT 0,
                reviews_count INTEGER NOT NULL DEFAULT 0,
                verification_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS service_categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS proof_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                photo_id INTEGER REFERENCES photos(id) ON DELETE SET NULL,
                uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
                file_type TEXT NOT NULL,
                storage_url TEXT NOT NULL,
                cid TEXT NOT NULL,
                room_or_area_label TEXT,
                notes TEXT,
                validation_status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        for column_sql in [
            "ALTER TABLE users ADD COLUMN first_name TEXT",
            "ALTER TABLE users ADD COLUMN last_name TEXT",
            "ALTER TABLE users ADD COLUMN profile_photo_url TEXT",
            "ALTER TABLE users ADD COLUMN location TEXT",
            "ALTER TABLE users ADD COLUMN service_area TEXT",
            "ALTER TABLE users ADD COLUMN payment_token_preference TEXT",
            "ALTER TABLE audit_events ADD COLUMN hcs_status TEXT NOT NULL DEFAULT 'local_only'",
            "ALTER TABLE audit_events ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'",
        ]:
            try:
                conn.execute(column_sql)
            except sqlite3.OperationalError:
                pass
        conn.executemany(
            "INSERT OR IGNORE INTO service_categories (id, name, slug, description) VALUES (:id, :name, :slug, :description)",
            marketplace_service.SERVICE_CATEGORIES,
        )


@app.on_event("startup")
def startup() -> None:
    init_db()
    logger.info("app.startup db_path=%s upload_dir=%s", DB_PATH, UPLOAD_DIR)


@app.get("/")
def root():
    return {"app": "EscrowEye", "status": "ok", "version": "0.1.0"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "healthy"}

app.include_router(create_homes_router(db=db, one=one, now_iso=now_iso, current_user=current_user, room_payload=room_payload))
app.include_router(
    create_jobs_router(
        db=db,
        one=one,
        now_iso=now_iso,
        current_user=current_user,
        public_user=public_user,
        add_audit=add_audit,
        base_dir=BASE_DIR,
        upload_dir=UPLOAD_DIR,
        openrouter_api_key=OPENROUTER_API_KEY,
        openrouter_model=OPENROUTER_MODEL,
        x402_service=x402_service,
    )
)
app.include_router(
    create_service_requests_router(
        db=db,
        one=one,
        now_iso=now_iso,
        current_user=current_user,
        public_user=public_user,
        x402_service=x402_service,
    )
)
app.include_router(create_quotes_router(db=db, one=one, now_iso=now_iso, current_user=current_user))
app.include_router(create_escrow_router(db=db, one=one, now_iso=now_iso, current_user=current_user))
app.include_router(create_proof_router(db=db, one=one, now_iso=now_iso, current_user=current_user, upload_dir=UPLOAD_DIR))
app.include_router(create_ai_validation_router(db=db, one=one, now_iso=now_iso, current_user=current_user))
app.include_router(create_earnings_router(db=db, current_user=current_user))
app.include_router(create_audit_router(db=db, one=one, current_user=current_user))
