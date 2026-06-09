from __future__ import annotations

import time
from typing import Any

import httpx
from app.core.config import settings


class X402ConfigurationError(RuntimeError):
    pass


class X402Service:
    def __init__(self, http_client: Any | None = None) -> None:
        self._http_client = http_client

    @property
    def require_real(self) -> bool:
        return settings.X402_REQUIRE_REAL

    @property
    def facilitator_url(self) -> str | None:
        return settings.X402_FACILITATOR_URL

    def payment_requirements(self) -> dict[str, Any]:
        return settings.x402_payment_requirements()

    def has_payment(self, headers: dict[str, str]) -> bool:
        return self._payment_header(headers) is not None

    def authorize_headers(self, headers: dict[str, str]) -> dict[str, Any]:
        payment = self._payment_header(headers)
        if not payment:
            return {"valid": False, "error": "missing_payment", "payment_requirements": self.payment_requirements()}
        if not self.require_real:
            return {"valid": True, "facilitator": settings.X402_FACILITATOR, "mode": "local"}
        return self.verify({"payment": payment, "payment_requirements": self.payment_requirements()})

    def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.require_real:
            return {"valid": True, "facilitator": settings.X402_FACILITATOR, "payload": payload}
        return self._post_to_facilitator("verify", payload)

    def settle(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.require_real:
            return self._post_to_facilitator("settle", payload)
        return {"settled": True, "hedera_tx_id": f"local:x402:{int(time.time())}", "payload": payload}

    def _payment_header(self, headers: dict[str, str]) -> str | None:
        normalized = {key.lower(): value for key, value in headers.items()}
        return normalized.get("x-payment") or normalized.get("x-402-payment") or normalized.get("payment")

    def _post_to_facilitator(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.facilitator_url:
            raise X402ConfigurationError("missing_x402_facilitator_url")
        url = f"{self.facilitator_url.rstrip('/')}/{path}"
        client = self._http_client or httpx.Client()
        response = client.post(url, json=payload, timeout=20)
        if isinstance(response, dict):
            return response
        response.raise_for_status()
        return response.json()
