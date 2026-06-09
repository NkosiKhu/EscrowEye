from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.infrastructure.hcs_service import HCSConfigurationError, HCSResult, HCSService
from app.infrastructure.x402_service import X402ConfigurationError, X402Service
from tests.conftest import make_client


def test_hcs_real_mode_requires_credentials(monkeypatch) -> None:
    monkeypatch.setenv("HEDERA_HCS_REQUIRE_REAL", "true")
    monkeypatch.delenv("HEDERA_OPERATOR_ID", raising=False)
    monkeypatch.delenv("HEDERA_OPERATOR_KEY", raising=False)
    monkeypatch.delenv("HEDERA_HCS_TOPIC_ID", raising=False)

    with pytest.raises(HCSConfigurationError):
        HCSService().submit_event("service_request_created", {"job_id": 1})


def test_hcs_real_mode_submits_through_client_factory(monkeypatch) -> None:
    monkeypatch.setenv("HEDERA_HCS_REQUIRE_REAL", "true")
    monkeypatch.setenv("HEDERA_OPERATOR_ID", "0.0.123")
    monkeypatch.setenv("HEDERA_OPERATOR_KEY", "operator-key")
    monkeypatch.setenv("HEDERA_HCS_TOPIC_ID", "0.0.456")

    class FakeHCSClient:
        def submit_message(self, topic_id: str, message: str) -> HCSResult:
            assert topic_id == "0.0.456"
            assert "service_request_created" in message
            return HCSResult(status="submitted", tx_id="0.0.123@1.000000001", topic_id=topic_id)

    result = HCSService(client_factory=lambda *_: FakeHCSClient()).submit_event("service_request_created", {"job_id": 1})

    assert result.status == "submitted"
    assert result.tx_id == "0.0.123@1.000000001"


def test_hcs_local_mode_falls_back_when_client_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("HEDERA_HCS_REQUIRE_REAL", raising=False)
    monkeypatch.setenv("HEDERA_OPERATOR_ID", "0.0.123")
    monkeypatch.setenv("HEDERA_OPERATOR_KEY", "operator-key")
    monkeypatch.setenv("HEDERA_HCS_TOPIC_ID", "0.0.456")

    def unavailable_client(*_: str):
        raise HCSConfigurationError("sdk_unavailable")

    result = HCSService(client_factory=unavailable_client).submit_event("service_request_created", {"job_id": 1})

    assert result.status == "pending_hcs"
    assert result.topic_id == "0.0.456"


def test_x402_real_mode_requires_facilitator(monkeypatch) -> None:
    monkeypatch.setenv("X402_REQUIRE_REAL", "true")
    monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)

    with pytest.raises(X402ConfigurationError):
        X402Service().authorize_headers({"x-payment": "opaque-payment"})


def test_x402_real_mode_authorizes_through_facilitator(monkeypatch) -> None:
    monkeypatch.setenv("X402_REQUIRE_REAL", "true")
    monkeypatch.setenv("X402_FACILITATOR_URL", "https://facilitator.example")

    class FakeHTTPClient:
        def post(self, url: str, json: dict, timeout: int) -> dict:
            assert url == "https://facilitator.example/verify"
            assert json["payment"] == "opaque-payment"
            assert timeout == 20
            return {"valid": True, "hedera_tx_id": "0.0.1@2.000000003"}

    result = X402Service(http_client=FakeHTTPClient()).authorize_headers({"x-payment": "opaque-payment"})

    assert result["valid"] is True
    assert result["hedera_tx_id"] == "0.0.1@2.000000003"


def test_service_request_rejects_unverified_x402_in_real_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("X402_REQUIRE_REAL", "true")
    monkeypatch.delenv("X402_FACILITATOR_URL", raising=False)
    client = make_client(tmp_path)

    challenge = client.post("/api/auth/challenge", json={"hedera_account_id": "0.0.7001"})
    token = client.post(
        "/api/auth/login",
        json={
            "hedera_account_id": "0.0.7001",
            "hedera_public_key": "dev-key",
            "signature": f"sig-{challenge.json()['nonce']}",
            "nonce": challenge.json()["nonce"],
            "user_type": "owner",
        },
    ).json()["token"]

    response = client.post(
        "/api/service-requests",
        headers={"Authorization": f"Bearer {token}", "X-PAYMENT": "opaque-payment"},
        json={
            "title": "Strict x402 request",
            "description": "Should fail without facilitator.",
            "address": "Ikoyi",
            "budget_amount": 100_000_000,
            "category": "cleaning",
        },
    )

    assert response.status_code == 402
    detail = response.json() if isinstance(response.json(), dict) and "error" in response.json() else response.json().get("detail", response.json())
    assert detail["error"] == "payment_verification_required"
