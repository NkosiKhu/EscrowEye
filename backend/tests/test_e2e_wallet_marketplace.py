from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main


OWNER_WALLET = os.getenv("ESCROWEYE_E2E_OWNER_WALLET", "0.0.910001")
SUPPLIER_WALLET = os.getenv("ESCROWEYE_E2E_SUPPLIER_WALLET", "0.0.920001")


def make_client(tmp_path: Path) -> TestClient:
    main.DB_PATH = tmp_path / "escroweye-e2e.sqlite3"
    main.UPLOAD_DIR = tmp_path / "uploads"
    main.init_db()
    return TestClient(main.app)


def wallet_login(client: TestClient, wallet: str, role: str) -> str:
    challenge = client.post("/api/auth/challenge", json={"hedera_account_id": wallet})
    assert challenge.status_code == 200
    nonce = challenge.json()["nonce"]
    login = client.post(
        "/api/auth/login",
        json={
            "hedera_account_id": wallet,
            "hedera_public_key": f"pub-{wallet}",
            "signature": f"dev-signature-for-{nonce}",
            "nonce": nonce,
            "user_type": role,
        },
    )
    assert login.status_code == 200
    assert login.json()["user"]["hedera_account_id"] == wallet
    assert login.json()["user"]["user_type"] == role
    return login.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.e2e
def test_wallet_owner_supplier_marketplace_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = wallet_login(client, OWNER_WALLET, "owner")
    supplier_token = wallet_login(client, SUPPLIER_WALLET, "supplier")

    owner_me = client.get("/api/auth/me", headers=auth(owner_token))
    supplier_me = client.get("/api/auth/me", headers=auth(supplier_token))
    assert owner_me.json()["hedera_account_id"] == OWNER_WALLET
    assert supplier_me.json()["hedera_account_id"] == SUPPLIER_WALLET

    created = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "E2E wallet window cleaning",
            "description": "Clean all windows and upload proof for AI validation.",
            "address": "10b Gerrard Road, Ikoyi, Lagos",
            "location_description": "Two-storey building",
            "schedule": "Sat, 1 Mar 2025",
            "budget_amount": 200_000_000,
            "category": "cleaning",
        },
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    quoted = client.post(
        f"/api/service-requests/{request_id}/quotes",
        headers=auth(supplier_token),
        json={"amount": 220_000_000, "message": "Can complete this weekend.", "scope": "Windows and frames", "timeline": "1 day"},
    )
    assert quoted.status_code == 201
    quote_id = quoted.json()["id"]

    accepted = client.post(f"/api/quotes/{quote_id}/accept", headers=auth(owner_token))
    funded = client.post(f"/api/service-requests/{request_id}/fund-escrow", headers=auth(owner_token), json={})
    assert accepted.status_code == 200
    assert funded.status_code == 200

    proof = client.post(
        f"/api/service-requests/{request_id}/proof",
        headers=auth(supplier_token),
        files={"files": ("after-clean.jpg", b"wallet e2e proof image", "image/jpeg")},
        data={"room_or_area_label": "Exterior windows", "notes": "All requested windows cleaned."},
    )
    assert proof.status_code == 201

    validation = client.post(f"/api/service-requests/{request_id}/ai-validation/run", headers=auth(owner_token))
    confirmed = client.post(f"/api/service-requests/{request_id}/confirm-satisfaction", headers=auth(owner_token), json={})
    released = client.post(f"/api/service-requests/{request_id}/release-payment", headers=auth(owner_token), json={})
    assert validation.status_code == 200
    assert validation.json()["status"] == "passed"
    assert confirmed.status_code == 200
    assert released.status_code == 200
    assert released.json()["escrow_status"] == "released"

    detail = client.get(f"/api/service-requests/{request_id}", headers=auth(owner_token))
    audit = client.get(f"/api/service-requests/{request_id}/audit-events", headers=auth(owner_token))
    assert detail.json()["owner"]["hedera_account_id"] == OWNER_WALLET
    assert detail.json()["supplier"]["hedera_account_id"] == SUPPLIER_WALLET
    assert "payment_released" in [event["type"] for event in audit.json()["events"]]
