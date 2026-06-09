"""Real testnet tests. Run with: HEDERA_NETWORK=testnet pytest tests/test_hedera_testnet.py -v"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("HEDERA_NETWORK") != "testnet",
    reason="Set HEDERA_NETWORK=testnet to run real testnet tests",
)


def test_escrow_cycle():
    """Create escrow with dev supplier key → fund via dev owner → release to dev supplier."""
    from app.services.escrow import EscrowService
    from app.services.hedera_client import get_dev_id, get_dev_key

    svc = EscrowService()
    supplier_pub = get_dev_key("supplier").public_key()

    escrow_id = svc.create_escrow_account_with_public_keys(str(supplier_pub))
    assert escrow_id.startswith("0.0.")

    balance = svc.get_balance(escrow_id)
    assert balance == 0

    owner_id = get_dev_id("owner")
    owner_key = get_dev_key("owner")
    from hiero_sdk_python import AccountId, Hbar, TransferTransaction

    client = svc.client
    tx = TransferTransaction()
    tx.add_hbar_transfer(AccountId.from_string(str(owner_id)), -1_00000000)
    tx.add_hbar_transfer(AccountId.from_string(escrow_id), 1_00000000)
    tx.freeze_with(client)
    tx.sign(owner_key)
    tx.execute(client)

    balance = svc.get_balance(escrow_id)
    assert balance == 1_00000000

    supplier_id = str(get_dev_id("supplier"))
    svc.release_escrow(escrow_id, supplier_id, 1_00000000)

    balance = svc.get_balance(escrow_id)
    assert balance < 1_000000
