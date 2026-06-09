from __future__ import annotations

import asyncio
import time

from hiero_sdk_python import (
    AccountCreateTransaction,
    AccountId,
    Hbar,
    PrivateKey,
    PublicKey,
    Transaction,
    TransferTransaction,
)

from hiero_sdk_python.crypto.key_list import KeyList

from .hedera_client import get_client, get_operator_key, get_operator_id, public_key_from_any


def verify_hedera_signature(public_key_str: str, signature_hex: str, message_str: str) -> bool:
    try:
        sig_bytes = bytes.fromhex(signature_hex) if not signature_hex.startswith("0x") else bytes.fromhex(signature_hex[2:])
        msg_bytes = message_str.encode("utf-8")
        pub_key = PublicKey.from_string(public_key_str)
        pub_key.verify(sig_bytes, msg_bytes)
        return True
    except Exception:
        return False


class EscrowService:
    def __init__(self) -> None:
        self.client = get_client()
        self.operator_key = get_operator_key()
        self.operator_id = get_operator_id()

    @staticmethod
    def _parse_public_key(raw: str) -> PublicKey:
        try:
            return PublicKey.from_string(raw)
        except Exception:
            pass
        try:
            return PublicKey.from_string_der(raw)
        except Exception:
            pass
        raw_bytes = bytes.fromhex(raw)
        try:
            if raw_bytes[0] == 0x30:
                raw_bytes = raw_bytes[-33:]
            return PublicKey.from_string(raw_bytes.hex())
        except Exception:
            pass
        raise ValueError(f"Cannot parse public key: {raw[:32]}...")

    def create_escrow_account_with_public_keys(self, supplier_public_key: str) -> str:
        # supplier_public_key kept for API compatibility and future multi-sig use;
        # escrow is currently 1-of-1 operator-only KeyList.
        threshold_key = KeyList(
            keys=[self.operator_key.public_key()],
            threshold=1,
        )

        tx = AccountCreateTransaction()
        tx.set_key(threshold_key)
        tx.set_initial_balance(Hbar.from_tinybars(0))
        tx.freeze_with(self.client)

        tx.sign(self.operator_key)
        receipt = tx.execute(self.client)
        return str(receipt.account_id)

    def release_escrow(
        self,
        escrow_account_id: str,
        to_account_id: str,
        amount_tinybar: int,
    ) -> str:
        escrow_id = AccountId.from_string(escrow_account_id)
        to_id = AccountId.from_string(to_account_id)

        tx = TransferTransaction()
        tx.add_hbar_transfer(escrow_id, -amount_tinybar)
        tx.add_hbar_transfer(to_id, amount_tinybar)
        tx.freeze_with(self.client)
        tx.sign(self.operator_key)
        resp = tx.execute(self.client)
        return str(resp.transaction_id)

    def fund_from_dev_owner(self, escrow_account_id: str, amount_tinybar: int) -> str:
        """Fund escrow from the DEV_OWNER account (Mode 2 — server-side, no wallet).
        Reads DEV_OWNER_PRIVATE_KEY and DEV_OWNER_ID from environment.
        Only used when HEDERA_NETWORK=testnet|mainnet and no client wallet is present."""
        from .hedera_client import get_dev_id, get_dev_key
        owner_key = get_dev_key("owner")
        owner_id = get_dev_id("owner")
        escrow_id = AccountId.from_string(escrow_account_id)
        tx = TransferTransaction()
        tx.add_hbar_transfer(owner_id, -amount_tinybar)
        tx.add_hbar_transfer(escrow_id, amount_tinybar)
        tx.freeze_with(self.client)
        tx.sign(owner_key)
        resp = tx.execute(self.client)
        return str(resp.transaction_id)

    async def poll_balance(self, account_id: str, target_amount: int, timeout_secs: int = 30) -> bool:
        deadline = time.time() + timeout_secs
        while time.time() < deadline:
            balance = self.get_balance(account_id)
            if balance >= target_amount:
                return True
            await asyncio.sleep(2)
        return False

    def submit_signed_transaction(self, signed_tx_bytes: bytes) -> dict:
        tx = Transaction.from_bytes(signed_tx_bytes)
        tx.sign(self.operator_key)
        receipt = tx.execute(self.client)
        return {
            "transaction_id": str(getattr(receipt, "transaction_id", "")),
            "status": str(getattr(receipt, "status", "")),
        }

    def get_balance(self, account_id: str) -> int:
        from hiero_sdk_python import CryptoGetAccountBalanceQuery

        query = CryptoGetAccountBalanceQuery()
        query.set_account_id(AccountId.from_string(account_id))
        balance = query.execute(self.client)
        return balance.hbars.to_tinybars()
