from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519

from tests.conftest import make_client


def test_login_requires_valid_ed25519_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ESCROWEYE_AUTH_REQUIRE_SIGNATURE", "true")
    client = make_client(tmp_path)
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw().hex()

    challenge = client.post("/api/auth/challenge", json={"hedera_account_id": "0.0.777001"})
    message = challenge.json()["message"].encode("utf-8")
    signature = private_key.sign(message).hex()

    response = client.post(
        "/api/auth/login",
        json={
            "hedera_account_id": "0.0.777001",
            "hedera_public_key": public_key,
            "signature": signature,
            "nonce": challenge.json()["nonce"],
            "user_type": "owner",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["hedera_account_id"] == "0.0.777001"


def test_login_rejects_invalid_signature_when_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ESCROWEYE_AUTH_REQUIRE_SIGNATURE", "true")
    client = make_client(tmp_path)
    private_key = ed25519.Ed25519PrivateKey.generate()
    other_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw().hex()

    challenge = client.post("/api/auth/challenge", json={"hedera_account_id": "0.0.777002"})
    signature = other_key.sign(challenge.json()["message"].encode("utf-8")).hex()

    response = client.post(
        "/api/auth/login",
        json={
            "hedera_account_id": "0.0.777002",
            "hedera_public_key": public_key,
            "signature": signature,
            "nonce": challenge.json()["nonce"],
            "user_type": "owner",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_wallet_signature"
