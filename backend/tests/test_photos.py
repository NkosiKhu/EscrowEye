from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import db, one


def _create_photo(
    conn,
    job_id: int,
    room_id: int | None,
    filename: str,
    storage_path: str,
    review_status: str = "pending",
    sequence: int = 1,
) -> int:
    cur = conn.execute(
        "INSERT INTO photos (job_id, room_id, uploaded_by_user_id, cid, filename, content_type, storage_path, sequence, review_status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id,
            room_id,
            1,
            "test-cid",
            filename,
            "image/jpeg",
            storage_path,
            sequence,
            review_status,
            "2025-01-01T00:00:00Z",
        ),
    )
    conn.commit()
    return cur.lastrowid


def test_upload_photo(
    client: TestClient,
    seeded_job: dict,
    auth_headers: dict,
):
    job_id = seeded_job["job_id"]

    file_bytes = b"fake-image-data"
    files = {"photos": ("test-photo.jpg", io.BytesIO(file_bytes), "image/jpeg")}
    resp = client.post(
        f"/api/jobs/{job_id}/photos",
        files=files,
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["photos"]) == 1
    photo = data["photos"][0]
    assert photo["review_status"] == "pending"
    assert photo["sequence"] == 1


def test_upload_photo_with_room(
    client: TestClient,
    seeded_job: dict,
    auth_headers: dict,
):
    job_id = seeded_job["job_id"]
    room_id = seeded_job["rooms"][0]["id"]

    file_bytes = b"fake-image-data"
    files = {"photos": ("living-room.jpg", io.BytesIO(file_bytes), "image/jpeg")}
    resp = client.post(
        f"/api/jobs/{job_id}/photos",
        files=files,
        data={"room_id": str(room_id)},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["photos"]) == 1


def test_patch_photo(
    client: TestClient,
    seeded_job: dict,
    auth_headers: dict,
    db_conn,
):
    job_id = seeded_job["job_id"]

    photo_id = _create_photo(
        db_conn,
        job_id,
        room_id=None,
        filename="test.jpg",
        storage_path="uploads/test.jpg",
    )

    resp = client.patch(
        f"/api/jobs/{job_id}/photos/{photo_id}",
        json={"review_status": "passed", "review_notes": "Looks good"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["review_status"] == "passed"
    assert data["review_notes"] == "Looks good"


def test_review_photos_mock_llm(
    seeded_job: dict,
    db_conn,
    tmp_path,
):
    import app.config
    from app.routers.photos import review_photos

    app.config.OPENROUTER_API_KEY = "fake-key"
    job_id = seeded_job["job_id"]
    living_room = seeded_job["rooms"][0]

    photo_path = tmp_path / "test-photo.jpg"
    photo_path.write_bytes(b"fake-image-data")
    storage_path = str(photo_path.relative_to(tmp_path))

    photo_id = _create_photo(
        db_conn, job_id, room_id=None, filename="living-room.jpg",
        storage_path=storage_path,
    )

    mock_response = {
        "room_id": living_room["id"],
        "room_name": "Living Room",
        "pass": True,
        "issues": [],
        "confidence": 0.95,
        "cleanliness_score": 5,
    }

    with patch("app.routers.photos.openrouter_review_photo", return_value=mock_response):
        review_photos(db_conn, job_id, [photo_id])

    photo = one(db_conn, "SELECT * FROM photos WHERE id = ?", (photo_id,))
    assert photo["review_status"] == "passed"
    assert "Living Room" in photo["review_notes"]
    assert photo["room_id"] == living_room["id"]


def test_review_photos_no_api_key(
    seeded_job: dict,
    db_conn,
    tmp_path,
):
    import app.config
    from app.routers.photos import review_photos

    app.config.OPENROUTER_API_KEY = None
    job_id = seeded_job["job_id"]

    photo_path = tmp_path / "test-photo.jpg"
    photo_path.write_bytes(b"fake-image-data")

    photo_id = _create_photo(
        db_conn, job_id, room_id=None, filename="dirty-kitchen.jpg",
        storage_path="uploads/test-photo.jpg",
    )

    review_photos(db_conn, job_id, [photo_id])

    photo = one(db_conn, "SELECT * FROM photos WHERE id = ?", (photo_id,))
    assert photo["review_status"] == "needs_retake"
    assert "retake" in photo["review_notes"].lower()


def test_review_photos_clean_fallback(
    seeded_job: dict,
    db_conn,
    tmp_path,
):
    import app.config
    from app.routers.photos import review_photos

    app.config.OPENROUTER_API_KEY = None
    job_id = seeded_job["job_id"]

    photo_id = _create_photo(
        db_conn, job_id, room_id=None, filename="clean-kitchen.jpg",
        storage_path="uploads/test-photo.jpg",
    )

    review_photos(db_conn, job_id, [photo_id])

    photo = one(db_conn, "SELECT * FROM photos WHERE id = ?", (photo_id,))
    assert photo["review_status"] == "passed"
    assert "clean" in photo["review_notes"].lower()
