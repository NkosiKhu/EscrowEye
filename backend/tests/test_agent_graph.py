from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.graph import (
    ReviewState,
    fetch_context,
    notify_owner,
    request_retry,
    review_photos,
    route_after_review,
    route_from_wait,
    wait_for_new_photo,
)


def _make_state(**overrides) -> ReviewState:
    state: ReviewState = {
        "job_id": 1,
        "status": "pending",
        "attempt_count": 0,
        "max_attempts": 3,
        "messages": [],
        "room_results": {},
        "job": None,
        "rooms": [],
        "photos": [],
        "summary": None,
        "failures": [],
    }
    state.update(overrides)
    return state


class TestFetchContext:
    @patch("agent.graph.db")
    def test_fetch_context(self, mock_db):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        mock_conn.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=MagicMock(
                __getitem__=lambda self, k: {0: 1, "id": 1, "home_id": 1}.get(k, "" if isinstance(k, str) else 0),
                keys=lambda: ["id", "home_id"],
            ))),
            MagicMock(fetchall=MagicMock(return_value=[])),
            MagicMock(fetchall=MagicMock(return_value=[])),
            MagicMock(fetchall=MagicMock(return_value=[])),
        ]

        state = _make_state(job_id=1)
        result = fetch_context(state)
        assert result["job"] is not None
        assert result["job"]["id"] == 1
        assert result["rooms"] == []
        assert result["photos"] == []
        assert result["messages"] == []


@pytest.fixture
def mock_llm():
    with patch("agent.graph.ChatOpenRouter") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_load_image():
    with patch("agent.graph._load_image_b64") as mock:
        mock.return_value = "fake_base64_image_data"
        yield mock


class TestReviewPhotos:
    def test_route_after_review_all_clear(self):
        state = _make_state(status="all_clear")
        assert route_after_review(state) == "notify_owner"

    def test_route_after_review_retry(self):
        state = _make_state(status="waiting_for_retry")
        assert route_after_review(state) == "request_retry"

    def test_route_from_wait_escalate(self):
        state = _make_state(attempt_count=3, max_attempts=3)
        assert route_from_wait(state) == "__end__"

    def test_route_from_wait_retry(self):
        state = _make_state(attempt_count=1, max_attempts=3)
        assert route_from_wait(state) == "fetch_context"

    @patch("agent.graph.db")
    def test_review_photos_all_pass(self, mock_db, mock_llm, mock_load_image):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        stage1_response = json.dumps({
            "room_id": 1,
            "room_name": "Kitchen",
            "confidence": 0.95,
            "cleanliness_score": 5,
            "pass": True,
            "issues": [],
        })

        summary_response = json.dumps({
            "room_assignments": [
                {"photo_id": 1, "room_id": 1, "review_status": "passed"},
            ],
            "overall_pass": True,
            "retake_needed": [],
            "summary": "All clean.",
        })

        mock_llm.invoke.side_effect = [
            MagicMock(content=stage1_response),
            MagicMock(content=summary_response),
        ]

        state = _make_state(
            job_id=1,
            rooms=[{"id": 1, "name": "Kitchen", "sq_meters": 20}],
            photos=[{"id": 1, "storage_path": "/tmp/photo1.jpg", "sequence": 1}],
        )
        result = review_photos(state)
        assert result["status"] == "all_clear"
        assert result["summary"]["overall_pass"] is True
        assert result["attempt_count"] == 1

    @patch("agent.graph.db")
    def test_review_photos_fail(self, mock_db, mock_llm, mock_load_image):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        stage1_response = json.dumps({
            "room_id": 1,
            "room_name": "Kitchen",
            "confidence": 0.8,
            "cleanliness_score": 2,
            "pass": False,
            "issues": ["Dirty counters", "Floor needs mopping"],
        })

        summary_response = json.dumps({
            "room_assignments": [
                {"photo_id": 1, "room_id": 1, "review_status": "failed"},
            ],
            "overall_pass": False,
            "retake_needed": [
                {"room_id": 1, "room_name": "Kitchen", "reason": "Dirty counters"},
            ],
            "summary": "Kitchen needs retake.",
        })

        mock_llm.invoke.side_effect = [
            MagicMock(content=stage1_response),
            MagicMock(content=summary_response),
        ]

        state = _make_state(
            job_id=1,
            rooms=[{"id": 1, "name": "Kitchen", "sq_meters": 20}],
            photos=[{"id": 1, "storage_path": "/tmp/photo1.jpg", "sequence": 1}],
        )
        result = review_photos(state)
        assert result["status"] == "waiting_for_retry"
        assert result["summary"]["overall_pass"] is False
        assert len(result["failures"]) == 1
        assert result["attempt_count"] == 1

    @patch("agent.graph.db")
    def test_review_photos_parse_error(self, mock_db, mock_llm, mock_load_image):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        mock_llm.invoke.side_effect = [
            MagicMock(content="not json"),
            MagicMock(content="not json"),
        ]

        state = _make_state(
            job_id=1,
            rooms=[{"id": 1, "name": "Kitchen"}],
            photos=[{"id": 1, "storage_path": "/tmp/p1.jpg"}],
        )
        result = review_photos(state)
        assert result["status"] == "waiting_for_retry"
        assert result["attempt_count"] == 1


class TestNotifyAndRetry:
    @patch("agent.graph.db")
    def test_notify_owner(self, mock_db):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.execute.return_value = mock_cur
        mock_cur.lastrowid = 100
        mock_row = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_row.__getitem__ = lambda self, k: 100 if k == "id" else ""

        state = _make_state(job_id=1)
        result = notify_owner(state)
        assert result is state

    @patch("agent.graph.db")
    def test_request_retry(self, mock_db):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.execute.return_value = mock_cur
        mock_cur.lastrowid = 101

        state = _make_state(
            job_id=1,
            failures=[
                {"room_name": "Kitchen", "reason": "Dirty counters"},
                {"room_name": "Bathroom", "reason": "Mold found"},
            ],
        )
        result = request_retry(state)
        assert result is state

    @patch("agent.graph.db")
    def test_wait_for_new_photo_escalate(self, mock_db):
        mock_conn = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_conn

        state = _make_state(attempt_count=3, max_attempts=3)
        result = wait_for_new_photo(state)
        assert result is state
