from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException


PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "hedera:testnet",
    "amount": "10000000",
    "asset": "0.0.0",
    "payTo": "0.0.7162784",
    "maxTimeoutSeconds": 180,
    "extra": {"feePayer": "0.0.7162784"},
}


class JobService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        one: Callable,
        now_iso: Callable[[], str],
        public_user: Callable,
        add_audit: Callable,
        base_dir: Path,
        upload_dir: Path,
        openrouter_api_key: str | None,
        openrouter_model: str,
    ):
        self.conn = conn
        self.one = one
        self.now_iso = now_iso
        self.public_user = public_user
        self.add_audit = add_audit
        self.base_dir = base_dir
        self.upload_dir = upload_dir
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_model = openrouter_model

    def job_summary(self, job: sqlite3.Row) -> dict[str, Any]:
        home = self.one(self.conn, "SELECT id, name, address FROM homes WHERE id = ?", (job["home_id"],))
        owner = self.one(self.conn, "SELECT * FROM users WHERE id = ?", (job["owner_user_id"],))
        supplier = self.conn.execute("SELECT * FROM users WHERE id = ?", (job["supplier_user_id"],)).fetchone() if job["supplier_user_id"] else None
        bids = self.conn.execute("SELECT COUNT(*) c, MIN(amount_tinybar) m FROM bids WHERE job_id = ? AND status != 'withdrawn'", (job["id"],)).fetchone()
        return {
            "id": job["id"],
            "title": job["title"],
            "description": job["description"],
            "suggested_price_tinybar": job["suggested_price_tinybar"],
            "status": job["status"],
            "home": dict(home),
            "owner": {"id": owner["id"], "hedera_account_id": owner["hedera_account_id"]},
            "supplier": self.public_user(supplier),
            "bid_count": bids["c"],
            "lowest_bid_tinybar": bids["m"],
            "created_at": job["created_at"],
        }

    def job_detail(self, job_id: int) -> dict[str, Any]:
        job = self.one(self.conn, "SELECT * FROM jobs WHERE id = ?", (job_id,))
        data = self.job_summary(job)
        accepted = self.conn.execute("SELECT id, amount_tinybar FROM bids WHERE id = ?", (job["accepted_bid_id"],)).fetchone() if job["accepted_bid_id"] else None
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

    def bid_payload(self, bid: sqlite3.Row) -> dict[str, Any]:
        supplier = self.one(self.conn, "SELECT * FROM users WHERE id = ?", (bid["supplier_user_id"],))
        return {
            "id": bid["id"],
            "supplier": {"id": supplier["id"], "hedera_account_id": supplier["hedera_account_id"]},
            "amount_tinybar": bid["amount_tinybar"],
            "message": bid["message"],
            "status": bid["status"],
            "created_at": bid["created_at"],
        }

    def insert_message(self, job_id: int, sender_user_id: int | None, sender_type: str, body: str, photo_ids: list[int]) -> sqlite3.Row:
        cur = self.conn.execute(
            "INSERT INTO messages (job_id, sender_user_id, sender_type, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, sender_user_id, sender_type, body, self.now_iso()),
        )
        for photo_id in photo_ids:
            self.one(self.conn, "SELECT id FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id))
            self.conn.execute("INSERT OR IGNORE INTO message_photos (message_id, photo_id) VALUES (?, ?)", (cur.lastrowid, photo_id))
        return self.one(self.conn, "SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))

    def message_payload(self, msg: sqlite3.Row) -> dict[str, Any]:
        sender = self.conn.execute("SELECT * FROM users WHERE id = ?", (msg["sender_user_id"],)).fetchone() if msg["sender_user_id"] else None
        photo_rows = self.conn.execute(
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
            "sender": self.public_user(sender),
            "sender_type": msg["sender_type"],
            "body": msg["body"],
            "photo_ids": [p["id"] for p in photo_rows],
            "photos": [dict(p) for p in photo_rows],
            "created_at": msg["created_at"],
        }

    def list_jobs(self, status: str | None, role: str | None, user: dict[str, Any]) -> dict[str, Any]:
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
        return {"jobs": [self.job_summary(row) for row in self.conn.execute(query, tuple(args)).fetchall()]}

    def create_job(self, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM homes WHERE id = ? AND owner_user_id = ?", (body.home_id, user["id"]))
        cur = self.conn.execute(
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
                self.now_iso(),
                self.now_iso(),
            ),
        )
        self.add_audit(self.conn, cur.lastrowid, "job_created")
        return {"id": cur.lastrowid, "status": "bidding", "creation_fee_paid": True, "hcs_topic_id": self.job_detail(cur.lastrowid)["hcs_topic_id"]}

    def list_bids(self, job_id: int) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        bids = self.conn.execute("SELECT * FROM bids WHERE job_id = ? AND status != 'withdrawn' ORDER BY amount_tinybar", (job_id,)).fetchall()
        return {"bids": [self.bid_payload(row) for row in bids]}

    def create_bid(self, job_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        cur = self.conn.execute(
            "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, message, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (job_id, user["id"], body.amount_tinybar, body.message, self.now_iso(), self.now_iso()),
        )
        return {"id": cur.lastrowid, "amount_tinybar": body.amount_tinybar, "status": "pending"}

    def update_bid(self, bid_id: int, body: Any, user: dict[str, Any]) -> dict[str, Any]:
        bid = self.one(self.conn, "SELECT * FROM bids WHERE id = ? AND supplier_user_id = ?", (bid_id, user["id"]))
        if bid["status"] != "pending":
            raise HTTPException(status_code=409, detail="bid_not_editable")
        self.conn.execute(
            "UPDATE bids SET amount_tinybar = ?, message = ?, updated_at = ? WHERE id = ?",
            (body.amount_tinybar, body.message, self.now_iso(), bid_id),
        )
        return {"id": bid_id, "amount_tinybar": body.amount_tinybar, "status": "pending"}

    def delete_bid(self, bid_id: int, user: dict[str, Any]) -> None:
        self.one(self.conn, "SELECT * FROM bids WHERE id = ? AND supplier_user_id = ?", (bid_id, user["id"]))
        self.conn.execute("UPDATE bids SET status = 'withdrawn', updated_at = ? WHERE id = ?", (self.now_iso(), bid_id))

    def award_job(self, job_id: int, bid_id: int, user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        bid = self.one(self.conn, "SELECT * FROM bids WHERE id = ? AND job_id = ? AND status = 'pending'", (bid_id, job_id))
        self.conn.execute("UPDATE bids SET status = CASE WHEN id = ? THEN 'accepted' ELSE 'rejected' END WHERE job_id = ?", (bid_id, job_id))
        self.conn.execute(
            "UPDATE jobs SET supplier_user_id = ?, accepted_bid_id = ?, status = 'awarded', updated_at = ? WHERE id = ?",
            (bid["supplier_user_id"], bid_id, self.now_iso(), job_id),
        )
        supplier = self.one(self.conn, "SELECT * FROM users WHERE id = ?", (bid["supplier_user_id"],))
        return {"job_id": job_id, "status": "awarded", "supplier": self.public_user(supplier)}

    def fund_job(self, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
        job = self.one(self.conn, "SELECT * FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        if not job["accepted_bid_id"]:
            raise HTTPException(status_code=409, detail="no_accepted_bid")
        bid = self.one(self.conn, "SELECT * FROM bids WHERE id = ?", (job["accepted_bid_id"],))
        escrow = f"0.0.{99990 + job_id}"
        self.conn.execute("UPDATE jobs SET status = 'funded', escrow_account_id = ?, updated_at = ? WHERE id = ?", (escrow, self.now_iso(), job_id))
        return {"job_id": job_id, "status": "funded", "escrow_account_id": escrow, "amount_tinybar": bid["amount_tinybar"]}

    def mark_ready(self, job_id: int, message: str | None, user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ? AND supplier_user_id = ?", (job_id, user["id"]))
        self.conn.execute("UPDATE jobs SET status = 'awaiting_confirmation', updated_at = ? WHERE id = ?", (self.now_iso(), job_id))
        if message:
            self.insert_message(job_id, user["id"], "human", message, [])
        return {"job_id": job_id, "status": "awaiting_confirmation"}

    def confirm_job(self, job_id: int, user: dict[str, Any]) -> dict[str, Any]:
        tx_hash = f"{user['hedera_account_id']}@{int(time.time())}.000000000"
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, user["id"]))
        self.conn.execute("UPDATE jobs SET status = 'completed', updated_at = ? WHERE id = ?", (self.now_iso(), job_id))
        self.add_audit(self.conn, job_id, "job_completed", tx_hash)
        return {"job_id": job_id, "status": "completed", "tx_hash": tx_hash}

    def dispute_job(self, job_id: int, reason: str, user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        self.conn.execute("UPDATE jobs SET status = 'disputed', updated_at = ? WHERE id = ?", (self.now_iso(), job_id))
        self.add_audit(self.conn, job_id, "job_disputed")
        self.insert_message(job_id, user["id"], "human", reason, [])
        return {"job_id": job_id, "status": "disputed"}

    def list_messages(self, job_id: int) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        messages = self.conn.execute("SELECT * FROM messages WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
        return {"messages": [self.message_payload(row) for row in messages]}

    def create_message(self, job_id: int, body: str, photo_ids: list[int], user: dict[str, Any]) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        msg = self.insert_message(job_id, user["id"], "human", body, photo_ids)
        if photo_ids:
            self.review_photos(job_id, photo_ids)
        return {
            "id": msg["id"],
            "sender_user_id": user["id"],
            "sender_type": "human",
            "body": msg["body"],
            "photo_ids": photo_ids,
            "created_at": msg["created_at"],
        }

    def mock_cid(self, content: bytes, filename: str) -> str:
        digest = hashlib.sha256(filename.encode() + b":" + content).hexdigest()
        return "bafy" + digest[:45]

    def create_photo_record(self, job_id: int, room_id: int | None, user_id: int, content: bytes, filename: str, content_type: str | None, encrypted_keys: str | None) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        if room_id is not None:
            self.one(self.conn, "SELECT id FROM rooms WHERE id = ?", (room_id,))
        seq = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM photos WHERE job_id = ?", (job_id,)).fetchone()[0] + 1
        cid = self.mock_cid(content, filename)
        suffix = Path(filename or "photo.bin").suffix or ".bin"
        storage_path = self.upload_dir / f"job-{job_id}-photo-{seq}-{cid[:16]}{suffix}"
        storage_path.write_bytes(content)
        try:
            stored_path = str(storage_path.relative_to(self.base_dir))
        except ValueError:
            stored_path = str(storage_path)
        cur = self.conn.execute(
            """
            INSERT INTO photos (
                job_id, room_id, uploaded_by_user_id, cid, filename, content_type, storage_path,
                sequence, review_status, encrypted_keys, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (job_id, room_id, user_id, cid, filename or storage_path.name, content_type, stored_path, seq, encrypted_keys, self.now_iso()),
        )
        return {"id": cur.lastrowid, "cid": cid, "sequence": seq, "review_status": "pending"}

    def photo_payload(self, photo: sqlite3.Row) -> dict[str, Any]:
        room = self.conn.execute("SELECT id, name FROM rooms WHERE id = ?", (photo["room_id"],)).fetchone() if photo["room_id"] else None
        uploaded_by = self.one(self.conn, "SELECT id, hedera_account_id FROM users WHERE id = ?", (photo["uploaded_by_user_id"],))
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

    def list_photos(self, job_id: int) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (job_id,))
        rows = self.conn.execute("SELECT * FROM photos WHERE job_id = ? ORDER BY sequence", (job_id,)).fetchall()
        return {"photos": [self.photo_payload(row) for row in rows]}

    def patch_photo(self, job_id: int, photo_id: int, body: Any) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM photos WHERE id = ? AND job_id = ?", (photo_id, job_id))
        if body.room_id is not None:
            self.one(self.conn, "SELECT id FROM rooms WHERE id = ?", (body.room_id,))
        self.conn.execute(
            """
            UPDATE photos
            SET room_id = COALESCE(?, room_id),
                review_status = COALESCE(?, review_status),
                review_notes = COALESCE(?, review_notes)
            WHERE id = ?
            """,
            (body.room_id, body.review_status, body.review_notes, photo_id),
        )
        photo = self.one(self.conn, "SELECT * FROM photos WHERE id = ?", (photo_id,))
        room = self.conn.execute("SELECT id, name FROM rooms WHERE id = ?", (photo["room_id"],)).fetchone() if photo["room_id"] else None
        return {"id": photo_id, "job_id": job_id, "room": dict(room) if room else None, "review_status": photo["review_status"], "review_notes": photo["review_notes"]}

    def audit_events(self, job_id: int) -> dict[str, Any]:
        job = self.one(self.conn, "SELECT hcs_topic_id FROM jobs WHERE id = ?", (job_id,))
        rows = self.conn.execute(
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

    def review_photos(self, job_id: int, photo_ids: list[int]) -> None:
        rooms = self.conn.execute(
            """
            SELECT r.id, r.name
            FROM rooms r JOIN jobs j ON j.home_id = r.home_id
            WHERE j.id = ? ORDER BY r.id
            """,
            (job_id,),
        ).fetchall()
        photos = self.conn.execute(
            f"SELECT * FROM photos WHERE job_id = ? AND id IN ({','.join('?' for _ in photo_ids)}) ORDER BY sequence",
            tuple([job_id] + photo_ids),
        ).fetchall()
        failures: list[str] = []
        for index, photo in enumerate(photos):
            filename = (photo["filename"] or "").lower()
            room = next((row for row in rooms if row["name"].lower() in filename), None)
            if room is None and rooms:
                room = rooms[index % len(rooms)]

            model_result = self.openrouter_review_photo(job_id, list(rooms), photo)
            if model_result:
                model_room_id = model_result.get("room_id")
                matched_room = next((row for row in rooms if row["id"] == model_room_id), None)
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
            self.conn.execute("UPDATE photos SET room_id = ?, review_status = ?, review_notes = ? WHERE id = ?", (room["id"] if room else None, status, notes, photo["id"]))
            if failed:
                failures.append(f"{room_name} needs a retake")
        summary = "Photo review: " + "; ".join(failures) + "." if failures else "Photo review: all uploaded rooms look clean. Ready for owner review."
        self.insert_message(job_id, None, "agent", summary, [])
        self.insert_message(job_id, None, "system", "Automated photo review completed.", [])

    def openrouter_review_photo(self, job_id: int, rooms: list[sqlite3.Row], photo: sqlite3.Row) -> dict[str, Any] | None:
        if not self.openrouter_api_key:
            return None
        path = self.base_dir / photo["storage_path"]
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
            "model": self.openrouter_model,
            "temperature": 0,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}}]}],
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
