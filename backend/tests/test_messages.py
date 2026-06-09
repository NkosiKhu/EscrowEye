from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database import one


def _create_photo(conn, job_id: int, filename: str = "test.jpg") -> int:
    cur = conn.execute(
        "INSERT INTO photos (job_id, room_id, uploaded_by_user_id, cid, filename, content_type, storage_path, sequence, review_status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, None, 1, "test-cid", filename, "image/jpeg", "uploads/test.jpg", 1, "pending", "2025-01-01T00:00:00Z"),
    )
    conn.commit()
    return cur.lastrowid


def test_create_message_no_photos(
    client: TestClient,
    seeded_job: dict,
    auth_headers: dict,
    db_conn,
):
    job_id = seeded_job["job_id"]
    resp = client.post(
        f"/api/jobs/{job_id}/messages",
        json={"body": "Hello, no photos here", "photo_ids": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["body"] == "Hello, no photos here"
    assert data["photo_ids"] == []

    row = one(db_conn, "SELECT * FROM messages WHERE id = ?", (data["id"],))
    assert row["body"] == "Hello, no photos here"


@pytest.mark.asyncio
async def test_create_message_with_photos(
    tmp_db,
    seeded_job: dict,
    auth_headers: dict,
    db_conn,
):
    from app.main import app
    import httpx

    job_id = seeded_job["job_id"]
    photo_id = _create_photo(db_conn, job_id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("app.routers.messages.trigger_review", None),
            patch("app.routers.messages.run_review", new_callable=AsyncMock) as mock_run_review,
        ):
            resp = await ac.post(
                f"/api/jobs/{job_id}/messages",
                json={"body": "Check these", "photo_ids": [photo_id]},
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text

            await asyncio.sleep(0)

            mock_run_review.assert_awaited_once()
            call_args = mock_run_review.await_args
            assert call_args is not None
            assert call_args[0][0] == job_id
            assert call_args[0][1] == [photo_id]


@pytest.mark.asyncio
async def test_run_review_calls_review_photos():
    from app.routers.messages import run_review
    from app.routers.photos import review_photos

    with patch("app.routers.messages.run_in_threadpool") as mock_rit:
        await run_review(42, [1, 2])

    mock_rit.assert_awaited_once()
    args = mock_rit.await_args
    assert args is not None
    func = args[0][0]
    assert func is review_photos
    assert args[0][2] == 42
    assert args[0][3] == [1, 2]
