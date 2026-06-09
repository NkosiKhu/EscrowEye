from __future__ import annotations

import os
import time
from typing import Any


PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "hedera:testnet",
    "amount": "10000000",
    "asset": "0.0.0",
    "payTo": os.getenv("X402_PAY_TO", "0.0.7162784"),
    "maxTimeoutSeconds": 180,
    "extra": {"feePayer": os.getenv("X402_FEE_PAYER", "0.0.7162784")},
}


class X402Service:
    def payment_requirements(self) -> dict[str, Any]:
        return PAYMENT_REQUIREMENTS

    def has_payment(self, headers: dict[str, str]) -> bool:
        return bool(headers.get("x-payment") or headers.get("x-402-payment") or headers.get("payment"))

    def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"valid": True, "facilitator": os.getenv("X402_FACILITATOR", "blocky402-mock"), "payload": payload}

    def settle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"settled": True, "hedera_tx_id": f"local:x402:{int(time.time())}", "payload": payload}
