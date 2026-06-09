from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.ipfs_service import IPFSConfigurationError, IPFSService
from tests.conftest import auth, login, make_client


def test_ipfs_local_mode_returns_ipfs_storage_url(monkeypatch) -> None:
    monkeypatch.delenv("PINATA_JWT", raising=False)
    monkeypatch.delenv("IPFS_REQUIRE_REAL", raising=False)

    result = IPFSService().upload_file(b"proof bytes", "after.jpg", "image/jpeg", {"job_id": 1})

    assert result.cid.startswith("bafy")
    assert result.storage_url == f"ipfs://{result.cid}"
    assert result.gateway_url.endswith(f"/ipfs/{result.cid}")
    assert result.provider == "local"


def test_ipfs_real_mode_requires_pinata_jwt(monkeypatch) -> None:
    monkeypatch.setenv("IPFS_REQUIRE_REAL", "true")
    monkeypatch.delenv("PINATA_JWT", raising=False)

    with pytest.raises(IPFSConfigurationError):
        IPFSService().upload_file(b"proof bytes", "after.jpg", "image/jpeg", {"job_id": 1})


def test_ipfs_pinata_mode_posts_file_to_pinata(monkeypatch) -> None:
    monkeypatch.setenv("PINATA_JWT", "pinata-jwt")
    monkeypatch.setenv("PINATA_GATEWAY_URL", "https://example.mypinata.cloud")

    class FakeHTTPClient:
        def post(self, url: str, headers: dict, files: dict, data: dict, timeout: int):
            assert url == "https://api.pinata.cloud/pinning/pinFileToIPFS"
            assert headers == {"Authorization": "Bearer pinata-jwt"}
            assert files["file"] == ("after.jpg", b"proof bytes", "image/jpeg")
            assert '"name":"after.jpg"' in data["pinataMetadata"]
            assert data["pinataOptions"] == '{"cidVersion":1}'
            assert timeout == 60
            return {"IpfsHash": "bafyrealcid", "PinSize": 11}

    result = IPFSService(http_client=FakeHTTPClient()).upload_file(b"proof bytes", "after.jpg", "image/jpeg", {"job_id": 1})

    assert result.cid == "bafyrealcid"
    assert result.storage_url == "ipfs://bafyrealcid"
    assert result.gateway_url == "https://example.mypinata.cloud/ipfs/bafyrealcid"
    assert result.provider == "pinata"


def test_proof_upload_records_ipfs_url_and_keeps_local_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PINATA_JWT", raising=False)
    monkeypatch.delenv("IPFS_REQUIRE_REAL", raising=False)
    client = make_client(tmp_path)
    owner_token = login(client, "0.0.3010", "owner")
    supplier_token = login(client, "0.0.4010", "supplier")
    request_id = client.post(
        "/api/service-requests",
        headers={**auth(owner_token), "X-PAYMENT": "paid"},
        json={
            "title": "IPFS proof request",
            "description": "Upload proof to IPFS.",
            "address": "Ikoyi",
            "schedule": "Today",
            "budget_amount": 100_000_000,
            "category": "cleaning",
        },
    ).json()["id"]

    uploaded = client.post(
        f"/api/service-requests/{request_id}/proof",
        headers=auth(supplier_token),
        files={"files": ("after.jpg", b"ipfs proof image", "image/jpeg")},
        data={"room_or_area_label": "Kitchen", "notes": "Done"},
    )
    proof = client.get(f"/api/service-requests/{request_id}/proof", headers=auth(owner_token)).json()["proof"][0]

    assert uploaded.status_code == 201
    assert uploaded.json()["proof"][0]["storage_url"].startswith("ipfs://")
    assert proof["storage_url"].startswith("ipfs://")
    assert proof["gateway_url"].endswith(proof["cid"])
    assert proof["local_path"]
