from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, utils


def signature_required() -> bool:
    return os.getenv("ESCROWEYE_AUTH_REQUIRE_SIGNATURE", "false").lower() in {"1", "true", "yes", "on"}


def challenge_message(nonce: str) -> str:
    return f"Sign this message to login to EscrowEye: {nonce}"


def verify_wallet_signature(public_key: str, signature: str, message: str) -> bool:
    key_bytes = _decode_key_material(public_key)
    signature_bytes = _decode_key_material(signature)
    message_bytes = message.encode("utf-8")
    return _verify_ed25519(key_bytes, signature_bytes, message_bytes) or _verify_ecdsa(key_bytes, signature_bytes, message_bytes)


def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        if len(public_key) == 32:
            key = ed25519.Ed25519PublicKey.from_public_bytes(public_key)
        else:
            key = serialization.load_der_public_key(public_key)
            if not isinstance(key, ed25519.Ed25519PublicKey):
                return False
        key.verify(signature, message)
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def _verify_ecdsa(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        if len(public_key) in {33, 65}:
            key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), public_key)
        else:
            key = serialization.load_der_public_key(public_key)
            if not isinstance(key, ec.EllipticCurvePublicKey):
                return False
        if len(signature) == 64:
            r = int.from_bytes(signature[:32], "big")
            s = int.from_bytes(signature[32:], "big")
            signature = utils.encode_dss_signature(r, s)
        key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def _decode_key_material(value: str) -> bytes:
    cleaned = value.strip()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        pass
    for candidate in (cleaned, _pad_base64(cleaned)):
        try:
            return base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            continue
    raise ValueError("invalid_key_material")


def _pad_base64(value: str) -> str:
    return value + "=" * (-len(value) % 4)
