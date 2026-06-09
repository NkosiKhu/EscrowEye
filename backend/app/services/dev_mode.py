from __future__ import annotations

import os

from fastapi import Request
from hiero_sdk_python import AccountId, PrivateKey, TransferTransaction

from .hedera_client import get_client

X402_FEE_COLLECTOR = "0.0.7162784"
X402_AMOUNT_TINYBAR = 10_000_000


def is_dev_mode(request: Request) -> bool:
    return request.headers.get("x-dev-mode", "").lower() == "true"


def get_dev_private_key(user_type: str) -> str:
    key_var = f"DEV_{user_type.upper()}_PRIVATE_KEY"
    raw = os.getenv(key_var, "")
    if raw.startswith("0x"):
        raw = raw[2:]
    return raw


def get_dev_account_id(user_type: str) -> str:
    id_var = f"DEV_{user_type.upper()}_ID"
    return os.getenv(id_var, "0.0.2")


def auto_pay_x402(owner_private_key: str) -> str:
    client = get_client()
    from_id = AccountId.from_string(get_dev_account_id("owner"))
    to_id = AccountId.from_string(X402_FEE_COLLECTOR)
    from_key = PrivateKey.from_string_ecdsa(owner_private_key)

    tx = TransferTransaction()
    tx.add_hbar_transfer(from_id, -X402_AMOUNT_TINYBAR)
    tx.add_hbar_transfer(to_id, X402_AMOUNT_TINYBAR)
    tx.freeze_with(client)
    tx.sign(from_key)
    resp = tx.execute(client)
    return str(resp.transaction_id)
