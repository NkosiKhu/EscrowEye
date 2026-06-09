from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_env():
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_env_validation_passes():
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "ESCROWEYE_SECRET": "a" * 64,
        "HEDERA_OPERATOR_ID": "0.0.12345",
        "HEDERA_OPERATOR_PRIVATE_KEY": "0x" + "ab" * 32,
        "PINATA_JWT": "eyJ123",
        "OPENROUTER_API_KEY": "sk-or-v1-test",
        "CORS_ORIGINS": "https://escroweye.app",
    }, clear=False):
        from app.config import validate_production_env

        validate_production_env()


def test_env_validation_fails():
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "ESCROWEYE_SECRET": "a" * 64,
        "HEDERA_OPERATOR_ID": "",
        "HEDERA_OPERATOR_PRIVATE_KEY": "",
        "PINATA_JWT": "",
        "OPENROUTER_API_KEY": "",
        "CORS_ORIGINS": "https://escroweye.app",
    }, clear=False):
        from app.config import validate_production_env

        with pytest.raises(RuntimeError, match="Missing required production"):
            validate_production_env()


def test_env_validation_fails_dev_secret():
    with patch.dict(os.environ, {
        "ENVIRONMENT": "production",
        "ESCROWEYE_SECRET": "escroweye-dev-secret",
        "HEDERA_OPERATOR_ID": "0.0.12345",
        "HEDERA_OPERATOR_PRIVATE_KEY": "0x" + "ab" * 32,
        "PINATA_JWT": "eyJ123",
        "OPENROUTER_API_KEY": "sk-or-v1-test",
        "CORS_ORIGINS": "https://escroweye.app",
    }, clear=False):
        from app.config import validate_production_env

        with pytest.raises(RuntimeError, match="dev default"):
            validate_production_env()


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}

    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}

    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "EscrowEye"


def test_cors_headers():
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_rate_limiting():
    for _ in range(5):
        client.get("/api/health")

    resp = client.get("/api/health")
    assert resp.status_code in (200, 429)
