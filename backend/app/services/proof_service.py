from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from app.services import marketplace as marketplace_service


class ProofService:
    def __init__(self, conn: sqlite3.Connection, *, one: Callable, now_iso: Callable[[], str], upload_dir: Path):
        self.conn = conn
        self.one = one
        self.now_iso = now_iso
        self.upload_dir = upload_dir

    def create_proof_record(self, request_id: int, user_id: int, content: bytes, filename: str, content_type: str | None, room_or_area_label: str | None, notes: str | None) -> dict[str, Any]:
        self.one(self.conn, "SELECT id FROM jobs WHERE id = ?", (request_id,))
        seq = self.conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM photos WHERE job_id = ?", (request_id,)).fetchone()[0] + 1
        cid = marketplace_service.mock_cid(content, filename)
        suffix = Path(filename or "proof.bin").suffix or ".bin"
        storage_path = self.upload_dir / f"request-{request_id}-proof-{seq}-{cid[:16]}{suffix}"
        storage_path.write_bytes(content)
        cur = self.conn.execute(
            """
            INSERT INTO photos (
                job_id, room_id, uploaded_by_user_id, cid, filename, content_type, storage_path,
                sequence, review_status, review_notes, encrypted_keys, created_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, 'pending', ?, '{}', ?)
            """,
            (request_id, user_id, cid, filename or storage_path.name, content_type, str(storage_path), seq, notes or room_or_area_label, self.now_iso()),
        )
        self.conn.execute(
            """
            INSERT INTO proof_uploads (
                job_id, photo_id, uploaded_by_user_id, file_type, storage_url, cid,
                room_or_area_label, notes, validation_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                request_id,
                cur.lastrowid,
                user_id,
                "video" if (content_type or "").startswith("video/") else "image",
                str(storage_path),
                cid,
                room_or_area_label,
                notes,
                self.now_iso(),
            ),
        )
        return {"id": cur.lastrowid, "cid": cid, "sequence": seq, "validation_status": "pending"}

    def mark_uploaded(self, request_id: int, count: int) -> None:
        self.conn.execute("UPDATE jobs SET status = 'proof_uploaded', updated_at = ? WHERE id = ?", (self.now_iso(), request_id))
        marketplace_service.add_local_audit(self.conn, request_id, "proof_uploaded", {"count": count})

    def list_proof(self, request_id: int) -> dict[str, Any]:
        rows = self.conn.execute("SELECT * FROM proof_uploads WHERE job_id = ? ORDER BY id", (request_id,)).fetchall()
        return {"proof": [dict(row) for row in rows]}

    def update_proof(self, request_id: int, proof_id: int, body: Any) -> dict[str, Any]:
        proof = self.one(self.conn, "SELECT * FROM proof_uploads WHERE id = ? AND job_id = ?", (proof_id, request_id))
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
            (body.room_id, body.review_status, body.review_notes, proof["photo_id"]),
        )
        if body.review_status is not None:
            self.conn.execute("UPDATE proof_uploads SET validation_status = ? WHERE id = ?", (body.review_status, proof_id))
        photo = self.one(self.conn, "SELECT * FROM photos WHERE id = ?", (proof["photo_id"],))
        room = self.conn.execute("SELECT id, name FROM rooms WHERE id = ?", (photo["room_id"],)).fetchone() if photo["room_id"] else None
        return {"id": proof_id, "photo_id": proof["photo_id"], "job_id": request_id, "room": dict(room) if room else None, "review_status": photo["review_status"], "review_notes": photo["review_notes"]}
