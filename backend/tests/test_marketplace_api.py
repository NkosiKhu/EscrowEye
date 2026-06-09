from __future__ import annotations

from pathlib import Path

from tests.conftest import auth, login, make_client


def test_service_categories_and_workers_are_open_for_marketplace(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    categories = client.get("/api/service-categories")
    workers = client.get("/api/workers?category=cleaning&location=Ikoyi")

    assert categories.status_code == 200
    assert "Cleaning" in [item["name"] for item in categories.json()["categories"]]
    assert workers.status_code == 200
    assert workers.json()["workers"][0]["rating"] >= 4


def test_owner_creates_paid_service_request_and_supplier_quote_is_accepted(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1001", "owner")
    supplier_token = login(client, "0.0.2001", "supplier")

    request_response = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "Window cleaning services",
            "description": "Clean exterior windows and upload proof.",
            "address": "10b Gerrard Road, Ikoyi, Lagos",
            "location_description": "Two-storey building",
            "schedule": "Sat, 1 Mar 2025",
            "budget_amount": 200_000_000,
            "category": "cleaning",
        },
    )
    assert request_response.status_code == 201
    request_id = request_response.json()["id"]

    quote = client.post(
        f"/api/service-requests/{request_id}/quotes",
        headers=auth(supplier_token),
        json={"amount": 220_000_000, "message": "Can complete this weekend.", "scope": "Windows and frames", "timeline": "1 day"},
    )
    assert quote.status_code == 201

    accepted = client.post(f"/api/quotes/{quote.json()['id']}/accept", headers=auth(owner_token))

    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "quote_accepted"
    assert body["quote_amount"] == 220_000_000
    assert body["base_commitment_fee"] == 44_000_000


def test_escrow_proof_ai_validation_and_release_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1002", "owner")
    supplier_token = login(client, "0.0.2002", "supplier")

    request_id = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "Airbnb turnover clean",
            "description": "Clean and document all rooms.",
            "address": "45 Adeola Odeku Street",
            "schedule": "Tue, 4 Mar 2025",
            "budget_amount": 300_000_000,
            "category": "airbnb",
        },
    ).json()["id"]
    quote_id = client.post(
        f"/api/service-requests/{request_id}/quotes",
        headers=auth(supplier_token),
        json={"amount": 250_000_000, "message": "Ready.", "scope": "Full turnover", "timeline": "same day"},
    ).json()["id"]
    client.post(f"/api/quotes/{quote_id}/accept", headers=auth(owner_token))
    assert client.post(f"/api/service-requests/{request_id}/fund-escrow", headers=auth(owner_token), json={}).status_code == 200

    proof = client.post(
        f"/api/service-requests/{request_id}/proof",
        headers=auth(supplier_token),
        files={"files": ("kitchen-clean.jpg", b"fake image", "image/jpeg")},
        data={"room_or_area_label": "Kitchen", "notes": "After-clean proof"},
    )
    assert proof.status_code == 201

    validation = client.post(f"/api/service-requests/{request_id}/ai-validation/run", headers=auth(owner_token))
    assert validation.status_code == 200
    assert validation.json()["status"] == "passed"

    confirmed = client.post(f"/api/service-requests/{request_id}/confirm-satisfaction", headers=auth(owner_token), json={})
    released = client.post(f"/api/service-requests/{request_id}/release-payment", headers=auth(owner_token), json={})

    assert confirmed.status_code == 200
    assert released.status_code == 200
    assert released.json()["escrow_status"] == "released"


def test_supplier_job_lists_and_earnings_use_role_specific_views(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1003", "owner")
    supplier_token = login(client, "0.0.2003", "supplier")

    request_id = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "Pool cleaning",
            "description": "Clean and inspect pool.",
            "address": "Banana Island",
            "schedule": "Fri, 7 Mar 2025",
            "budget_amount": 120_000_000,
            "category": "pool-cleaning",
        },
    ).json()["id"]
    quote_id = client.post(
        f"/api/service-requests/{request_id}/quotes",
        headers=auth(supplier_token),
        json={"amount": 120_000_000, "message": "Available.", "scope": "Pool clean", "timeline": "2 hours"},
    ).json()["id"]

    offers = client.get("/api/supplier/jobs/offers", headers=auth(supplier_token))
    client.post(f"/api/quotes/{quote_id}/accept", headers=auth(owner_token))
    active = client.get("/api/supplier/jobs/active", headers=auth(supplier_token))
    earnings = client.get("/api/supplier/earnings", headers=auth(supplier_token))

    assert offers.status_code == 200
    assert active.status_code == 200
    assert active.json()["jobs"][0]["id"] == request_id
    assert earnings.status_code == 200
    assert "pending_earnings" in earnings.json()


def test_role_guards_block_wrong_marketplace_actions(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1010", "owner")
    supplier_token = login(client, "0.0.2010", "supplier")

    supplier_create = client.post(
        "/api/service-requests",
        headers={**auth(supplier_token), "X-PAYMENT": "paid"},
        json={
            "title": "Wrong role request",
            "description": "Supplier should not create owner request.",
            "address": "Ikoyi",
            "schedule": "Today",
            "budget_amount": 100_000_000,
            "category": "cleaning",
        },
    )
    assert supplier_create.status_code == 403

    owner_quote = client.post(
        "/api/service-requests/1/quotes",
        headers=auth(owner_token),
        json={"amount": 100_000_000, "message": "Owner should not quote"},
    )
    assert owner_quote.status_code == 403


def test_escrow_release_requires_quote_acceptance_and_validation(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1011", "owner")
    supplier_token = login(client, "0.0.2011", "supplier")

    request_id = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "Maintenance request",
            "description": "Fix and document work.",
            "address": "Lekki",
            "schedule": "Tomorrow",
            "budget_amount": 180_000_000,
            "category": "maintenance",
        },
    ).json()["id"]

    fund_too_early = client.post(f"/api/service-requests/{request_id}/fund-escrow", headers=auth(owner_token), json={})
    assert fund_too_early.status_code == 409

    quote_id = client.post(
        f"/api/service-requests/{request_id}/quotes",
        headers=auth(supplier_token),
        json={"amount": 180_000_000, "message": "I can do it."},
    ).json()["id"]
    client.post(f"/api/quotes/{quote_id}/accept", headers=auth(owner_token))
    client.post(f"/api/service-requests/{request_id}/fund-escrow", headers=auth(owner_token), json={})

    confirm_too_early = client.post(f"/api/service-requests/{request_id}/confirm-satisfaction", headers=auth(owner_token), json={})
    release_too_early = client.post(f"/api/service-requests/{request_id}/release-payment", headers=auth(owner_token), json={})

    assert confirm_too_early.status_code == 409
    assert release_too_early.status_code == 409


def test_proof_upload_changes_job_status_and_creates_audit_event(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.1012", "owner")
    supplier_token = login(client, "0.0.2012", "supplier")

    request_id = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "Proof status request",
            "description": "Upload proof.",
            "address": "Yaba",
            "schedule": "Friday",
            "budget_amount": 90_000_000,
            "category": "cleaning",
        },
    ).json()["id"]

    proof = client.post(
        f"/api/service-requests/{request_id}/proof",
        headers=auth(supplier_token),
        files={"files": ("after.jpg", b"proof", "image/jpeg")},
        data={"room_or_area_label": "Lounge", "notes": "Done"},
    )
    detail = client.get(f"/api/service-requests/{request_id}", headers=auth(owner_token))
    audit = client.get(f"/api/service-requests/{request_id}/audit-events", headers=auth(owner_token))

    assert proof.status_code == 201
    assert detail.json()["status"] == "proof_uploaded"
    assert "proof_uploaded" in [event["type"] for event in audit.json()["events"]]
