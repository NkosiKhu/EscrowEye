from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.tools import (
    API_BASE,
    associate_photo,
    award_bid,
    confirm_job,
    create_home,
    create_job,
    dispute_job,
    fund_escrow,
    get_bids,
    get_homes,
    get_job,
    get_jobs,
    get_messages,
    get_photos,
    mark_ready,
    place_bid,
    send_message,
    set_agent_jwt,
)


@pytest.fixture(autouse=True)
def _setup_jwt():
    set_agent_jwt("test-jwt")
    yield
    set_agent_jwt("")


@pytest.fixture
def mock_client():
    with patch("agent.tools.httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__.return_value = client_instance
        response_mock = MagicMock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {}
        client_instance.request = AsyncMock(return_value=response_mock)
        yield client_instance


_HEADERS = {"Authorization": "Bearer test-jwt", "X-Payment": "mock"}


@pytest.mark.asyncio
async def test_get_jobs(mock_client):
    mock_client.request.return_value.json.return_value = {"jobs": []}
    result = await get_jobs.ainvoke({"status": "bidding"})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs?status=bidding",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"jobs": []}


@pytest.mark.asyncio
async def test_get_jobs_no_filter(mock_client):
    mock_client.request.return_value.json.return_value = {"jobs": []}
    result = await get_jobs.ainvoke({})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"jobs": []}


@pytest.mark.asyncio
async def test_get_job(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 1, "title": "Test"}
    result = await get_job.ainvoke({"job_id": 1})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs/1",
        json=None,
        headers=_HEADERS,
    )
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_create_job(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 1, "title": "Clean House"}
    args = {
        "home_id": 1,
        "title": "Clean House",
        "description": "Full clean",
        "suggested_price_tinybar": 50000000,
    }
    result = await create_job.ainvoke(args)
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs",
        json={
            "home_id": 1,
            "title": "Clean House",
            "description": "Full clean",
            "suggested_price_tinybar": 50000000,
        },
        headers=_HEADERS,
    )
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_create_job_with_optional(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 2}
    args = {
        "home_id": 1,
        "title": "Deep Clean",
        "description": "Deep clean",
        "suggested_price_tinybar": 80000000,
        "access_notes": "Gate code 1234",
        "available_times": "Weekends",
    }
    result = await create_job.ainvoke(args)
    assert result["id"] == 2


@pytest.mark.asyncio
async def test_get_homes(mock_client):
    mock_client.request.return_value.json.return_value = {"homes": []}
    result = await get_homes.ainvoke({})
    mock_client.request.assert_called_once_with(
        "GET", "/api/homes",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"homes": []}


@pytest.mark.asyncio
async def test_create_home(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 1, "name": "My Home"}
    result = await create_home.ainvoke({"name": "My Home", "address": "123 Main St"})
    mock_client.request.assert_called_once_with(
        "POST", "/api/homes",
        json={"name": "My Home", "address": "123 Main St"},
        headers=_HEADERS,
    )
    assert result["name"] == "My Home"


@pytest.mark.asyncio
async def test_place_bid(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 5, "amount_tinybar": 100000000}
    result = await place_bid.ainvoke({"job_id": 3, "amount_tinybar": 100000000, "message": "I can do it"})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/bids",
        json={"amount_tinybar": 100000000, "message": "I can do it"},
        headers=_HEADERS,
    )
    assert result["id"] == 5


@pytest.mark.asyncio
async def test_place_bid_no_message(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 6}
    result = await place_bid.ainvoke({"job_id": 3, "amount_tinybar": 50000000})
    assert result["id"] == 6


@pytest.mark.asyncio
async def test_get_bids(mock_client):
    mock_client.request.return_value.json.return_value = {"bids": []}
    result = await get_bids.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs/3/bids",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"bids": []}


@pytest.mark.asyncio
async def test_award_bid(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "awarded"}
    result = await award_bid.ainvoke({"job_id": 3, "bid_id": 5})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/award",
        json={"bid_id": 5},
        headers=_HEADERS,
    )
    assert result["status"] == "awarded"


@pytest.mark.asyncio
async def test_fund_escrow(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "funded"}
    result = await fund_escrow.ainvoke({"job_id": 3, "transaction_id": "0.0.10001@1234567890.000000000"})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/fund",
        json={"transaction_id": "0.0.10001@1234567890.000000000"},
        headers=_HEADERS,
    )
    assert result["status"] == "funded"


@pytest.mark.asyncio
async def test_fund_escrow_bodyless(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "awaiting_funding"}
    result = await fund_escrow.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/fund",
        json=None,
        headers=_HEADERS,
    )
    assert result["status"] == "awaiting_funding"


@pytest.mark.asyncio
async def test_mark_ready(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "awaiting_confirmation"}
    result = await mark_ready.ainvoke({"job_id": 3, "message": "Done!"})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/mark-ready",
        json={"message": "Done!"},
        headers=_HEADERS,
    )
    assert result["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_mark_ready_no_message(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "awaiting_confirmation"}
    result = await mark_ready.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/mark-ready",
        json={},
        headers=_HEADERS,
    )
    assert result["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_send_message(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 10, "body": "Hello"}
    result = await send_message.ainvoke({"job_id": 3, "body": "Hello", "photo_ids": [1, 2]})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/messages",
        json={"body": "Hello", "photo_ids": [1, 2]},
        headers=_HEADERS,
    )
    assert result["body"] == "Hello"


@pytest.mark.asyncio
async def test_send_message_no_photos(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 11}
    result = await send_message.ainvoke({"job_id": 3, "body": "Hi"})
    assert result["id"] == 11


@pytest.mark.asyncio
async def test_get_messages(mock_client):
    mock_client.request.return_value.json.return_value = {"messages": []}
    result = await get_messages.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs/3/messages",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"messages": []}


@pytest.mark.asyncio
async def test_get_photos(mock_client):
    mock_client.request.return_value.json.return_value = {"photos": []}
    result = await get_photos.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "GET", "/api/jobs/3/photos",
        json=None,
        headers=_HEADERS,
    )
    assert result == {"photos": []}


@pytest.mark.asyncio
async def test_associate_photo(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 1, "room_id": 1, "review_status": "passed"}
    args = {"job_id": 3, "photo_id": 1, "room_id": 1, "review_status": "passed"}
    result = await associate_photo.ainvoke(args)
    mock_client.request.assert_called_once_with(
        "PATCH", "/api/jobs/3/photos/1",
        json={"room_id": 1, "review_status": "passed"},
        headers=_HEADERS,
    )
    assert result["review_status"] == "passed"


@pytest.mark.asyncio
async def test_associate_photo_with_notes(mock_client):
    mock_client.request.return_value.json.return_value = {"id": 1}
    args = {"job_id": 3, "photo_id": 1, "room_id": 2, "review_status": "failed", "review_notes": "Dirty counters"}
    result = await associate_photo.ainvoke(args)
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_confirm_job(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "completed"}
    result = await confirm_job.ainvoke({"job_id": 3})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/confirm",
        json=None,
        headers=_HEADERS,
    )
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_dispute_job(mock_client):
    mock_client.request.return_value.json.return_value = {"status": "disputed"}
    result = await dispute_job.ainvoke({"job_id": 3, "reason": "Work not done"})
    mock_client.request.assert_called_once_with(
        "POST", "/api/jobs/3/dispute",
        json={"reason": "Work not done"},
        headers=_HEADERS,
    )
    assert result["status"] == "disputed"


@pytest.mark.asyncio
async def test_api_call_no_jwt():
    set_agent_jwt("")
    with patch("agent.tools.httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__.return_value = client_instance
        response_mock = MagicMock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {"jobs": []}
        client_instance.request = AsyncMock(return_value=response_mock)
        result = await get_jobs.ainvoke({})
        client_instance.request.assert_called_once_with(
            "GET", "/api/jobs",
            json=None,
            headers={"X-Payment": "mock"},
        )
        assert result == {"jobs": []}
