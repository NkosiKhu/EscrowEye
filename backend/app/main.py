from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field


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
SECRET = os.getenv("ESCROWEYE_SECRET", "escroweye-dev-secret").encode()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")

app = FastAPI(title="EscrowEye API", version="0.1.0")
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
        return dict(one(conn, "SELECT * FROM users WHERE id = ?", (user_id,)))


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
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root():
    return {"app": "EscrowEye", "status": "ok", "version": "0.1.0"}


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "healthy"}


class ChallengeIn(BaseModel):
    hedera_account_id: str


class LoginIn(BaseModel):
    hedera_account_id: str
    hedera_public_key: str = ""
    signature: str = ""
    nonce: str
    user_type: str = Field(pattern="^(owner|supplier)$")


class ProfilePatch(BaseModel):
    email: Optional[str] = None


@app.post("/api/auth/challenge")
def challenge(body: ChallengeIn):
    nonce = secrets.token_hex(8)
    with db() as conn:
        conn.execute(
            "INSERT INTO challenges (nonce, hedera_account_id, created_at) VALUES (?, ?, ?)",
            (nonce, body.hedera_account_id, now_iso()),
        )
    return {"nonce": nonce, "message": f"Sign this message to login to EscrowEye: {nonce}"}


@app.post("/api/auth/login")
def login(body: LoginIn):
    with db() as conn:
        challenge_row = one(
            conn,
            "SELECT * FROM challenges WHERE nonce = ? AND hedera_account_id = ?",
            (body.nonce, body.hedera_account_id),
        )
        _ = challenge_row, body.signature
        existing = conn.execute("SELECT * FROM users WHERE hedera_account_id = ?", (body.hedera_account_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET hedera_public_key = COALESCE(NULLIF(?, ''), hedera_public_key), user_type = ? WHERE id = ?",
                (body.hedera_public_key, body.user_type, existing["id"]),
            )
            user = one(conn, "SELECT * FROM users WHERE id = ?", (existing["id"],))
        else:
            cur = conn.execute(
                """
                INSERT INTO users (email, user_type, hedera_account_id, hedera_public_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (None, body.user_type, body.hedera_account_id, body.hedera_public_key, now_iso()),
            )
            user = one(conn, "SELECT * FROM users WHERE id = ?", (cur.lastrowid,))
        conn.execute("DELETE FROM challenges WHERE nonce = ?", (body.nonce,))
        return {"token": token_for(user["id"]), "user": public_user(user)}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return public_user(user)


@app.patch("/api/auth/profile")
def profile(body: ProfilePatch, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        conn.execute("UPDATE users SET email = COALESCE(?, email) WHERE id = ?", (body.email, user["id"]))
        row = one(conn, "SELECT id, email FROM users WHERE id = ?", (user["id"],))
        return dict(row)


class HomeIn(BaseModel):
    name: str
    address: str


class RoomIn(BaseModel):
    name: str
    sq_meters: Optional[float] = None


def home_with_rooms(conn: sqlite3.Connection, home_id: int, owner_id: int | None = None) -> dict[str, Any]:
    if owner_id is None:
        home = one(conn, "SELECT * FROM homes WHERE id = ?", (home_id,))
    else:
        home = one(conn, "SELECT * FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, owner_id))
    rooms = conn.execute("SELECT id, name, sq_meters FROM rooms WHERE home_id = ? ORDER BY id", (home_id,)).fetchall()
    return {"id": home["id"], "name": home["name"], "address": home["address"], "rooms": [room_payload(r) for r in rooms]}


@app.get("/api/homes")
def list_homes(user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        homes = conn.execute("SELECT id FROM homes WHERE owner_user_id = ? ORDER BY id", (user["id"],)).fetchall()
        return {"homes": [home_with_rooms(conn, h["id"], user["id"]) for h in homes]}


@app.post("/api/homes")
def create_home(body: HomeIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO homes (owner_user_id, name, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], body.name, body.address, now_iso(), now_iso()),
        )
        return home_with_rooms(conn, cur.lastrowid, user["id"])


@app.get("/api/homes/{home_id}")
def get_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        return home_with_rooms(conn, home_id, user["id"])


@app.put("/api/homes/{home_id}")
def update_home(home_id: int, body: HomeIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, user["id"]))
        conn.execute("UPDATE homes SET name = ?, address = ?, updated_at = ? WHERE id = ?", (body.name, body.address, now_iso(), home_id))
        return {"id": home_id, "name": body.name, "address": body.address}


@app.delete("/api/homes/{home_id}", status_code=204)
def delete_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, user["id"]))
        conn.execute("DELETE FROM homes WHERE id = ?", (home_id,))
    return Response(status_code=204)


@app.post("/api/homes/{home_id}/rooms")
def create_room(home_id: int, body: RoomIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, user["id"]))
        cur = conn.execute("INSERT INTO rooms (home_id, name, sq_meters) VALUES (?, ?, ?)", (home_id, body.name, body.sq_meters))
        return room_payload(one(conn, "SELECT id, name, sq_meters FROM rooms WHERE id = ?", (cur.lastrowid,)))


@app.delete("/api/homes/{home_id}/rooms/{room_id}", status_code=204)
def delete_room(home_id: int, room_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, user["id"]))
        one(conn, "SELECT id FROM rooms WHERE id = ? AND home_id = ?", (room_id, home_id))
        conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
    return Response(status_code=204)


class JobIn(BaseModel):
    home_id: int
    title: str
    description: str
    suggested_price_tinybar: int
    access_notes: Optional[str] = None
    available_times: Optional[str] = None


PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "hedera:testnet",
    "amount": "10000000",
    "asset": "0.0.0",
    "payTo": "0.0.7162784",
    "maxTimeoutSeconds": 180,
    "extra": {"feePayer": "0.0.7162784"},
}


def job_summary(conn: sqlite3.Connection, job: sqlite3.Row) -> dict[str, Any]:
    home = one(conn, "SELECT id, name, address FROM homes WHERE id = ?", (job["home_id"],))
    owner = one(conn, "SELECT * FROM users WHERE id = ?", (job["owner_user_id"],))
    supplier = conn.execute("SELECT * FROM users WHERE id = ?", (job["supplier_user_id"],)).fetchone() if job["supplier_user_id"] else None
    bids = conn.execute("SELECT COUNT(*) c, MIN(amount_tinybar) m FROM bids WHERE job_id = ? AND status != 'withdrawn'", (job["id"],)).fetchone()
    return {
        "id": job["id"],
        "title": job["title"],
        "description": job["description"],
        "suggested_price_tinybar": job["suggested_price_tinybar"],
        "status": job["status"],
        "home": dict(home),
        "owner": {"id": owner["id"], "hedera_account_id": owner["hedera_account_id"]},
        "supplier": public_user(supplier),
        "bid_count": bids["c"],
        "lowest_bid_tinybar": bids["m"],
        "created_at": job["created_at"],
    }


def job_detail(conn: sqlite3.Connection, job_id: int) -> dict[str, Any]:
    job = one(conn, "SELECT * FROM jobs WHERE id = ?", (job_id,))
    data = job_summary(conn, job)
    accepted = conn.execute("SELECT id, amount_tinybar FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone() if job["accepted_bid_id"] else None
    data.update(
        {
            "access_notes": job["access_notes"],
            "available_times": job["available_times"],
            "escrow_account_id": job["escrow_account_id"],
            "hcs_topic_id": job["hcs_topic_id"],
            "accepted_bid": dict(accepted) if accepted else None,
            "creation_fee_paid": bool(job["creation_fee_paid"]),
            "updated_at": job["updated_at"],
        }
    )
    return data


@app.get("/api/jobs")
def list_jobs(status: str | None = None, role: str | None = None, user: dict[str, Any] = Depends(current_user)):
    query = "SELECT * FROM jobs WHERE 1 = 1"
    args: list[Any] = []
    if status:
        query += " AND status = ?"
        args.append(status)
    if role == "owned":
        query += " AND owner_user_id = ?"
        args.append(user["id"])
    elif role == "assigned":
        query += " AND supplier_user_id = ?"
        args.append(user["id"])
    query += " ORDER BY id DESC"
    with db() as conn:
        return {"jobs": [job_summary(conn, row) for row in conn.execute(query, tuple(args)).fetchall()]}


@app.post("/api/jobs", status_code=201)
def create_job(
    body: JobIn,
    request: Request,
    x_payment: str | None = Header(default=None),
    x_402_payment: str | None = Header(default=None),
    user: dict[str, Any] = Depends(current_user),
):
    if not (x_payment or x_402_payment or request.headers.get("Payment")):
        return JSONResponse(status_code=402, content={"error": "payment_required", "payment_requirements": PAYMENT_REQUIREMENTS})
    with db() as conn:
        one(conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (body.home_id, user["id"]))
        cur = conn.execute(
            """
            INSERT INTO jobs (
                home_id, owner_user_id, title, description, suggested_price_tinybar, access_notes,
                available_times, status, hcs_topic_id, creation_fee_paid, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'bidding', ?, 1, ?, ?)
            """,
            (
                body.home_id,
                user["id"],
                body.title,
                body.description,
                body.suggested_price_tinybar,
                body.access_notes,
                body.available_times,
                f"0.0.{88880 + int(time.time()) % 10000}",
                now_iso(),
                now_iso(),
            ),
        )
        add_audit(conn, cur.lastrowid, "job_created")
        return {"id": cur.lastrowid, "status": "bidding", "creation_fee_paid": True, "hcs_topic_id": job_detail(conn, cur.lastrowid)["hcs_topic_id"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        return job_detail(conn, job_id)


class BidIn(BaseModel):
    amount_tinybar: int
    message: Optional[str] = None


def bid_payload(conn: sqlite3.Connection, bid: sqlite3.Row) -> dict[str, Any]:
    supplier = one(conn, "SELECT * FROM users WHERE id = ?", (bid["supplier_user_id"],))
    return {
        "id": bid["id"],
        "supplier": {"id": supplier["id"], "hedera_account_id": supplier["hedera_account_id"]},
        "amount_tinybar": bid["amount_tinybar"],
        "message": bid["message"],
        "status": bid["status"],
        "created_at": bid["created_at"],
    }


@app.get("/api/jobs/{job_id}/bids")
def list_bids(job_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        bids = conn.execute("SELECT * FROM bids WHERE job_id = ? AND status != 'withdrawn' ORDER BY amount_tinybar", (job_id,)).fetchall()
        return {"bids": [bid_payload(conn, b) for b in bids]}


@app.post("/api/jobs/{job_id}/bids")
def create_bid(job_id: int, body: BidIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        cur = conn.execute(
            "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, message, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (job_id, user["id"], body.amount_tinybar, body.message, now_iso(), now_iso()),
        )
        return {"id": cur.lastrowid, "amount_tinybar": body.amount_tinybar, "status": "pending"}


@app.put("/api/bids/{bid_id}")
def update_bid(bid_id: int, body: BidIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        bid = one(conn, "SELECT * FROM bids WHERE id = ? AND supplier_user_id = ?", (bid_id, user["id"]))
        if bid["status"] != "pending":
            raise HTTPException(status_code=409, detail="bid_not_editable")
        conn.execute(
            "UPDATE bids SET amount_tinybar = ?, message = ?, updated_at = ? WHERE id = ?",
            (body.amount_tinybar, body.message, now_iso(), bid_id),
        )
        return {"id": bid_id, "amount_tinybar": body.amount_tinybar, "status": "pending"}


@app.delete("/api/bids/{bid_id}", status_code=204)
def delete_bid(bid_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT * FROM bids WHERE id = ? AND supplier_user_id = ?", (bid_id, user["id"]))
        conn.execute("UPDATE bids SET status = 'withdrawn', updated_at = ? WHERE id = ?", (now_iso(), bid_id))
    return Response(status_code=204)


class AwardIn(BaseModel):
    bid_id: int


@app.post("/api/jobs/{job_id}/award")
def award_job(job_id: int, body: AwardIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        bid = one(conn, "SELECT * FROM bids WHERE id = ? AND job_id = ? AND status = 'pending'", (body.bid_id, job_id))
        conn.execute("UPDATE bids SET status = CASE WHEN id = ? THEN 'accepted' ELSE 'rejected' END WHERE job_id = ?", (body.bid_id, job_id))
        conn.execute(
            "UPDATE jobs SET supplier_user_id = ?, accepted_bid_id = ?, status = 'awarded', updated_at = ? WHERE id = ?",
            (bid["supplier_user_id"], body.bid_id, now_iso(), job_id),
        )
        supplier = one(conn, "SELECT * FROM users WHERE id = ?", (bid["supplier_user_id"],))
        return {"job_id": job_id, "status": "awarded", "supplier": public_user(supplier)}


@app.post("/api/jobs/{job_id}/fund")
def fund_job(job_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
    _ = body
    with db() as conn:
        job = one(conn, "SELECT * FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        if not job["accepted_bid_id"]:
            raise HTTPException(status_code=409, detail="no_accepted_bid")
        bid = one(conn, "SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],))
        escrow = f"0.0.{99990 + job_id}"
        conn.execute("UPDATE jobs SET status = 'funded', escrow_account_id = ?, updated_at = ? WHERE id = ?", (escrow, now_iso(), job_id))
        return {"job_id": job_id, "status": "funded", "escrow_account_id": escrow, "amount_tinybar": bid["amount_tinybar"]}


class ReadyIn(BaseModel):
    message: Optional[str] = None


@app.post("/api/jobs/{job_id}/mark-ready")
def mark_ready(job_id: int, body: ReadyIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ? AND supplier_user_id = ?", (job_id, user["id"]))
        conn.execute("UPDATE jobs SET status = 'awaiting_confirmation', updated_at = ? WHERE id = ?", (now_iso(), job_id))
        if body.message:
            insert_message(conn, job_id, user["id"], "human", body.message, [])
        return {"job_id": job_id, "status": "awaiting_confirmation"}


@app.post("/api/jobs/{job_id}/confirm")
def confirm_job(job_id: int, body: dict[str, Any], user: dict[str, Any] = Depends(current_user)):
    _ = body
    tx_hash = f"{user['hedera_account_id']}@{int(time.time())}.000000000"
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        conn.execute("UPDATE jobs SET status = 'completed', updated_at = ? WHERE id = ?", (now_iso(), job_id))
        add_audit(conn, job_id, "job_completed", tx_hash)
        return {"job_id": job_id, "status": "completed", "tx_hash": tx_hash}


class DisputeIn(BaseModel):
    reason: str


@app.post("/api/jobs/{job_id}/dispute")
def dispute_job(job_id: int, body: DisputeIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        conn.execute("UPDATE jobs SET status = 'disputed', updated_at = ? WHERE id = ?", (now_iso(), job_id))
        add_audit(conn, job_id, "job_disputed")
        insert_message(conn, job_id, user["id"], "human", body.reason, [])
        return {"job_id": job_id, "status": "disputed"}


class MessageIn(BaseModel):
    body: str = ""
    photo_ids: list[int] = Field(default_factory=list)


def insert_message(
    conn: sqlite3.Connection,
    job_id: int,
    sender_user_id: int | None,
    sender_type: str,
    body: str,
    photo_ids: list[int],
) -> sqlite3.Row:
    cur = conn.execute(
        "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, sender_user_id, sender_type, body, now_iso()),
    )
    for photo_id in photo_ids:
        one(conn, "SELECT id FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id))
        conn.execute("INSERT OR IGNORE INTO message_photos (message_id, photo_id) VALUES (?, ?)", (cur.lastrowid, photo_id))
    return one(conn, "SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))


def message_payload(conn: sqlite3.Connection, msg: sqlite3.Row) -> dict[str, Any]:
    sender = conn.execute("SELECT * FROM users WHERE id = ?", (msg["sender_user_id"],)).fetchone() if msg["sender_user_id"] else None
    photo_rows = conn.execute(
        """
        SELECT p.id, p.cid, p.sequence
        FROM message_photos mp JOIN photos p ON p.id = mp.photo_id
        WHERE mp.message_id = ? ORDER BY p.sequence
        """,
        (msg["id"],),
    ).fetchall()
    return {
        "id": msg["id"],
        "sender_user_id": msg["sender_user_id"],
        "sender": public_user(sender),
        "sender_type": msg["sender_type"],
        "body": msg["body"],
        "photo_ids": [p["id"] for p in photo_rows],
        "photos": [dict(p) for p in photo_rows],
        "created_at": msg["created_at"],
    }


@app.get("/api/jobs/{job_id}/messages")
def list_messages(job_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        messages = conn.execute("SELECT * FROM messages WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
        return {"messages": [message_payload(conn, m) for m in messages]}


@app.post("/api/jobs/{job_id}/messages")
def create_message(job_id: int, body: MessageIn, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        msg = insert_message(conn, job_id, user["id"], "human", body.body, body.photo_ids)
        if body.photo_ids:
            review_photos(conn, job_id, body.photo_ids)
        return {
            "id": msg["id"],
            "sender_user_id": user["id"],
            "sender_type": "human",
            "body": msg["body"],
            "photo_ids": body.photo_ids,
            "created_at": msg["created_at"],
        }


def mock_cid(content: bytes, filename: str) -> str:
    digest = hashlib.sha256(filename.encode() + b":" + content).hexdigest()
    return "bafy" + digest[:45]


def photo_payload(conn: sqlite3.Connection, photo: sqlite3.Row) -> dict[str, Any]:
    room = conn.execute("SELECT id, name FROM rooms WHERE id = ?", (photo["room_id"],)).fetchone() if photo["room_id"] else None
    uploaded_by = one(conn, "SELECT id, hedera_account_id FROM users WHERE id = ?", (photo["uploaded_by_user_id"],))
    return {
        "id": photo["id"],
        "cid": photo["cid"],
        "room": dict(room) if room else None,
        "uploaded_by": dict(uploaded_by),
        "sequence": photo["sequence"],
        "review_status": photo["review_status"],
        "review_notes": photo["review_notes"],
        "created_at": photo["created_at"],
    }


@app.post("/api/jobs/{job_id}/photos")
async def upload_photos(
    job_id: int,
    photos: list[UploadFile] = File(...),
    room_id: int | None = Form(default=None),
    encrypted_keys: str | None = Form(default=None),
    user: dict[str, Any] = Depends(current_user),
):
    results = []
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        if room_id is not None:
            one(conn, "SELECT id FROM rooms WHERE id = ?", (room_id,))
        seq = conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM photos WHERE job_id = ?", (job_id,)).fetchone()[0]
        for upload in photos:
            content = await upload.read()
            cid = mock_cid(content, upload.filename or "photo")
            seq += 1
            suffix = Path(upload.filename or "photo.bin").suffix or ".bin"
            storage_path = UPLOAD_DIR / f"job-{job_id}-photo-{seq}-{cid[:16]}{suffix}"
            storage_path.write_bytes(content)
            try:
                stored_path = str(storage_path.relative_to(BASE_DIR))
            except ValueError:
                stored_path = str(storage_path)
            cur = conn.execute(
                """
                INSERT INTO photos (
                    job_id, room_id, uploaded_by_user_id, cid, filename, content_type, storage_path,
                    sequence, review_status, encrypted_keys, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    job_id,
                    room_id,
                    user["id"],
                    cid,
                    upload.filename or storage_path.name,
                    upload.content_type,
                    stored_path,
                    seq,
                    encrypted_keys,
                    now_iso(),
                ),
            )
            results.append({"id": cur.lastrowid, "cid": cid, "sequence": seq, "review_status": "pending"})
    return {"photos": results}


@app.get("/api/jobs/{job_id}/photos")
def list_photos(job_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        rows = conn.execute("SELECT * FROM photos WHERE job_id = ? ORDER BY sequence", (job_id,)).fetchall()
        return {"photos": [photo_payload(conn, p) for p in rows]}


class PhotoPatch(BaseModel):
    room_id: Optional[int] = None
    review_status: Optional[str] = Field(default=None, pattern="^(pending|passed|failed|needs_retake)$")
    review_notes: Optional[str] = None


@app.patch("/api/jobs/{job_id}/photos/{photo_id}")
def patch_photo(job_id: int, photo_id: int, body: PhotoPatch, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        one(conn, "SELECT id FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id))
        if body.room_id is not None:
            one(conn, "SELECT id FROM rooms WHERE id = ?", (body.room_id,))
        conn.execute(
            """
            UPDATE photos
            SET room_id = COALESCE(?, room_id),
                review_status = COALESCE(?, review_status),
                review_notes = COALESCE(?, review_notes)
            WHERE id = ?
            """,
            (body.room_id, body.review_status, body.review_notes, photo_id),
        )
        photo = one(conn, "SELECT * FROM photos WHERE id = ?", (photo_id,))
        room = conn.execute("SELECT id, name FROM rooms WHERE id = ?", (photo["room_id"],)).fetchone() if photo["room_id"] else None
        return {"id": photo_id, "job_id": job_id, "room": dict(room) if room else None, "review_status": photo["review_status"], "review_notes": photo["review_notes"]}


def review_photos(conn: sqlite3.Connection, job_id: int, photo_ids: list[int]) -> None:
    rooms = conn.execute(
        """
        SELECT r.id, r.name
        FROM rooms r JOIN jobs j ON j.home_id = r.home_id
        WHERE j.id = ? ORDER BY r.id
        """,
        (job_id,),
    ).fetchall()
    photos = conn.execute(
        f"SELECT * FROM photos WHERE job_id = ? AND id IN ({','.join('?' for _ in photo_ids)}) ORDER BY sequence",
        tuple([job_id] + photo_ids),
    ).fetchall()
    failures: list[str] = []
    for index, photo in enumerate(photos):
        filename = (photo["filename"] or "").lower()
        room = next((r for r in rooms if r["name"].lower() in filename), None)
        if room is None and rooms:
            room = rooms[index % len(rooms)]

        model_result = openrouter_review_photo(job_id, list(rooms), photo)
        if model_result:
            model_room_id = model_result.get("room_id")
            matched_room = next((r for r in rooms if r["id"] == model_room_id), None)
            if matched_room is not None:
                room = matched_room
            failed = not bool(model_result.get("pass"))
            issues = model_result.get("issues")
            issue_text = ", ".join(str(issue) for issue in issues) if isinstance(issues, list) and issues else "review did not pass"
            status = "needs_retake" if failed else "passed"
            room_name = room["name"] if room else str(model_result.get("room_name") or "the uploaded area")
            notes = f"{room_name} {'needs a retake: ' + issue_text if failed else 'looks clean based on OpenRouter review.'}"
        else:
            bad_words = ("dirty", "mess", "retake", "fail", "stain", "trash", "before")
            failed = any(word in filename for word in bad_words)
            status = "needs_retake" if failed else "passed"
            room_name = room["name"] if room else "the uploaded area"
            notes = f"{room_name} {'needs a retake based on mock review heuristics.' if failed else 'looks clean in the mock review.'}"
        conn.execute("UPDATE photos SET room_id = ?, review_status = ?, review_notes = ? WHERE id = ?", (room["id"] if room else None, status, notes, photo["id"]))
        if failed:
            failures.append(f"{room_name} needs a retake")
    if failures:
        summary = "Photo review: " + "; ".join(failures) + "."
        sender_type = "agent"
    else:
        summary = "Photo review: all uploaded rooms look clean. Ready for owner review."
        sender_type = "agent"
    insert_message(conn, job_id, None, sender_type, summary, [])
    insert_message(conn, job_id, None, "system", "Automated photo review completed.", [])


def openrouter_review_photo(job_id: int, rooms: list[sqlite3.Row], photo: sqlite3.Row) -> dict[str, Any] | None:
    if not OPENROUTER_API_KEY:
        return None
    path = BASE_DIR / photo["storage_path"]
    if not path.exists():
        return None

    room_list = [{"id": room["id"], "name": room["name"]} for room in rooms]
    image_data = base64.b64encode(path.read_bytes()).decode()
    mime_type = photo["content_type"] or "image/jpeg"
    prompt = (
        f"You are evaluating a cleaning photo for EscrowEye job #{job_id}.\n"
        f"Rooms to clean: {json.dumps(room_list)}\n"
        "Return JSON only with keys: room_id, room_name, confidence, cleanliness_score, pass, issues. "
        "Use one of the provided room ids when possible. pass must be true only when cleanliness_score is at least 4."
    )
    payload = {
        "model": OPENROUTER_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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


@app.get("/api/jobs/{job_id}/audit-events")
def audit_events(job_id: int, user: dict[str, Any] = Depends(current_user)):
    with db() as conn:
        job = one(conn, "SELECT hcs_topic_id FROM jobs WHERE id = ?", (job_id,))
        rows = conn.execute(
            "SELECT type, job_id, tx_hash, sequence_number, consensus_timestamp FROM audit_events WHERE job_id = ? ORDER BY sequence_number",
            (job_id,),
        ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            if item["tx_hash"] is None:
                item.pop("tx_hash")
            events.append(item)
        return {"hcs_topic_id": job["hcs_topic_id"], "events": events}
