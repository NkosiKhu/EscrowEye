from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def mock_escrow():
    with patch("app.services.escrow.EscrowService") as mock:
        instance = mock.return_value
        instance.create_escrow_account_with_public_keys.return_value = "0.0.12345"
        instance.submit_signed_transaction.return_value = {
            "transaction_id": "0.0.10001@1234567890.000000000",
            "status": "SUCCESS",
        }
        instance.release_escrow.return_value = "0.0.10001@1234567890.000000000"
        # poll_balance is now async — use AsyncMock so `await instance.poll_balance(...)` works
        from unittest.mock import AsyncMock
        instance.poll_balance = AsyncMock(return_value=True)
        yield instance


@pytest.fixture
def mock_hcs_success():
    with patch("app.services.hcs.HcsService") as mock:
        instance = mock.return_value
        instance.create_topic.return_value = "0.0.30001"
        yield instance


@pytest.fixture
def mock_hcs_failure():
    with patch("app.services.hcs.HcsService") as mock:
        instance = mock.return_value
        instance.create_topic.side_effect = Exception("HCS unavailable")
        yield instance


@pytest.fixture
def mock_dev_keys():
    with patch("app.services.dev_mode.get_dev_private_key") as mock_key, \
         patch("app.services.dev_mode.get_dev_account_id") as mock_id:
        mock_key.return_value = "0x" + "ab" * 32
        mock_id.return_value = "0.0.10001"
        yield mock_key, mock_id


def prepare_funded_job(db_conn, seeded_job):
    owner_id = seeded_job["owner_id"]
    supplier_id = seeded_job["supplier_id"]
    db_conn.execute(
        "UPDATE users SET hedera_public_key = ? WHERE id = ?",
        ("0x03" + "ab" * 31, owner_id),
    )
    db_conn.execute(
        "UPDATE users SET hedera_public_key = ? WHERE id = ?",
        ("0x03" + "cd" * 31, supplier_id),
    )
    db_conn.execute(
        "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (seeded_job["job_id"], supplier_id, 500000, "pending", "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    bid = db_conn.execute(
        "SELECT id FROM bids WHERE job_id = ?", (seeded_job["job_id"],)
    ).fetchone()
    db_conn.execute(
        "UPDATE jobs SET status = 'awarded', accepted_bid_id = ? WHERE id = ?",
        (bid["id"], seeded_job["job_id"]),
    )
    db_conn.commit()
    return bid


def test_fund_job_with_transaction_id(client, db_conn, seeded_job, mock_escrow, mock_dev_keys, auth_headers):
    prepare_funded_job(db_conn, seeded_job)
    resp = client.post(
        f"/api/jobs/{seeded_job['job_id']}/fund",
        json={"transaction_id": "0.0.10001@1234567890.000000000"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "funded"
    assert data["escrow_account_id"] == "0.0.12345"


def test_fund_job_dev_mode_bodyless(client, db_conn, seeded_job, mock_escrow, mock_dev_keys, auth_headers):
    prepare_funded_job(db_conn, seeded_job)
    resp = client.post(
        f"/api/jobs/{seeded_job['job_id']}/fund",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "funded"
    assert data["escrow_account_id"] == "0.0.12345"


def test_fund_job_no_accepted_bid(client, db_conn, seeded_job, mock_escrow, mock_dev_keys, auth_headers):
    resp = client.post(
        f"/api/jobs/{seeded_job['job_id']}/fund",
        json={"transaction_id": "0.0.10001@1234567890.000000000"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "no_accepted_bid"


def test_confirm_job_dev_mode(client, db_conn, seeded_job, auth_headers, mock_escrow, mock_dev_keys):
    owner_id = seeded_job["owner_id"]
    supplier_id = seeded_job["supplier_id"]
    db_conn.execute(
        "UPDATE users SET hedera_public_key = ? WHERE id = ?",
        ("0x03" + "ab" * 31, owner_id),
    )
    db_conn.execute(
        "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, status, created_at, updated_at) VALUES (?, ?, ?, 'accepted', ?, ?)",
        (seeded_job["job_id"], supplier_id, 500000, "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    bid = db_conn.execute(
        "SELECT id FROM bids WHERE job_id = ?", (seeded_job["job_id"],)
    ).fetchone()
    db_conn.execute(
        "UPDATE jobs SET status = 'awaiting_confirmation', escrow_account_id = '0.0.99999', accepted_bid_id = ? WHERE id = ?",
        (bid["id"], seeded_job["job_id"]),
    )
    db_conn.commit()
    resp = client.post(
        f"/api/jobs/{seeded_job['job_id']}/confirm",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["tx_hash"] is not None


def test_hcs_topic_creation_failure_production(client, db_conn, seeded_job, auth_headers, mock_hcs_failure):
    home_id = seeded_job["home_id"]
    resp = client.post(
        "/api/jobs",
        json={
            "home_id": home_id,
            "title": "Test HCS Failure",
            "description": "Should return 503",
            "suggested_price_tinybar": 1000000,
        },
        headers={
            **auth_headers,
            "x-payment": "0.0.10001@1234567890.000000000",
        },
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "hcs_unavailable"


def test_hcs_topic_creation_failure_dev_mode(client, db_conn, seeded_job, auth_headers, mock_hcs_failure):
    home_id = seeded_job["home_id"]
    resp = client.post(
        "/api/jobs",
        json={
            "home_id": home_id,
            "title": "Test HCS Failure Dev",
            "description": "Should use fake topic",
            "suggested_price_tinybar": 1000000,
        },
        headers={
            **auth_headers,
            "x-dev-mode": "true",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["hcs_topic_id"].startswith("0.0.")


def test_x402_payment_verification_valid(client, db_conn, seeded_job, auth_headers, mock_hcs_success):
    home_id = seeded_job["home_id"]
    resp = client.post(
        "/api/jobs",
        json={
            "home_id": home_id,
            "title": "Test X402 Payment",
            "description": "With payment header",
            "suggested_price_tinybar": 1000000,
        },
        headers={
            **auth_headers,
            "x-payment": "0.0.10001@1234567890.000000000",
        },
    )
    assert resp.status_code == 201


def test_x402_payment_missing_production(client, db_conn, seeded_job, auth_headers):
    home_id = seeded_job["home_id"]
    resp = client.post(
        "/api/jobs",
        json={
            "home_id": home_id,
            "title": "Test No Payment",
            "description": "Should fail",
            "suggested_price_tinybar": 1000000,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 402
    assert resp.json()["error"] == "payment_required"
