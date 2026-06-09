from __future__ import annotations

import os

from hiero_sdk_python import AccountId, Client, PrivateKey, PublicKey

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        network = os.getenv("HEDERA_NETWORK", "testnet")
        operator_id = AccountId.from_string(os.getenv("HEDERA_OPERATOR_ID", "0.0.2"))
        raw_key = os.getenv("HEDERA_OPERATOR_PRIVATE_KEY", "")
        if raw_key.startswith("0x"):
            raw_key = raw_key[2:]
        operator_key = PrivateKey.from_string_ecdsa(raw_key)
        if network == "testnet":
            _client = Client.for_testnet()
        elif network == "mainnet":
            _client = Client.for_mainnet()
        else:
            _client = Client.for_testnet()
        _client.set_operator(operator_id, operator_key)
    return _client


def get_operator_id() -> AccountId:
    raw = os.getenv("HEDERA_OPERATOR_ID", "0.0.2")
    return AccountId.from_string(raw)


def get_operator_key() -> PrivateKey:
    raw = os.getenv("HEDERA_OPERATOR_PRIVATE_KEY", "")
    if raw.startswith("0x"):
        raw = raw[2:]
    return PrivateKey.from_string_ecdsa(raw)


def get_dev_key(user_type: str) -> PrivateKey:
    key_var = f"DEV_{user_type.upper()}_PRIVATE_KEY"
    raw = os.getenv(key_var, "")
    return PrivateKey.from_string_ecdsa(raw)


def get_dev_id(user_type: str) -> AccountId:
    id_var = f"DEV_{user_type.upper()}_ID"
    raw = os.getenv(id_var, "0.0.2")
    return AccountId.from_string(raw)


def public_key_from_any(pub_key_str: str | None, priv_key_str: str | None = None) -> PublicKey:
    if priv_key_str:
        raw = priv_key_str
        if raw.startswith("0x"):
            raw = raw[2:]
        return PrivateKey.from_string(raw).public_key()
    if pub_key_str:
        try:
            return PublicKey.from_string(pub_key_str)
        except Exception:
            pass
        try:
            return PublicKey.from_string_der(pub_key_str)
        except Exception:
            pass
    raise ValueError("Cannot derive public key - no private key or valid public key string provided")
