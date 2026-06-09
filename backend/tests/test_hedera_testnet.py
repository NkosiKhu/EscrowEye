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


def test_marketplace_escrow_cycle():
    """Simulates the full UI flow: accept_quote creates escrow,
    fund_from_dev_owner sends HBAR, release_escrow pays supplier."""
    from app.services.escrow import EscrowService
    from app.services.hedera_client import get_dev_id, get_dev_key

    svc = EscrowService()
    supplier_pub = get_dev_key("supplier").public_key()

    # Step 1: accept_quote creates escrow
    escrow_id = svc.create_escrow_account_with_public_keys(str(supplier_pub))
    assert escrow_id.startswith("0.0.")

    # Step 2: fund_escrow uses dev owner key
    amount = 1_00000000  # 1 HBAR
    tx_id = svc.fund_from_dev_owner(escrow_id, amount)
    assert "@" in tx_id  # Hedera tx ID format: 0.0.X@timestamp

    # Step 3: balance confirmed
    balance = svc.get_balance(escrow_id)
    assert balance == amount

    # Step 4: release_payment sends to supplier
    supplier_id = str(get_dev_id("supplier"))
    release_tx = svc.release_escrow(escrow_id, supplier_id, amount)
    assert "@" in release_tx

    # Balance drained
    assert svc.get_balance(escrow_id) < 1_000000
