# EscrowEye Wallet E2E Test

This backend E2E test runs the full owner-to-supplier marketplace flow:

1. Owner wallet logs in.
2. Supplier wallet logs in.
3. Owner creates a paid service request.
4. Supplier submits a quote.
5. Owner accepts and funds escrow.
6. Supplier uploads proof.
7. AI validation passes.
8. Owner confirms satisfaction.
9. Escrow releases payment.
10. Audit events are checked.

Run with default local wallet-like account IDs:

```bash
cd backend
.venv/bin/python -m pytest tests/test_e2e_wallet_marketplace.py -q
```

Run with real Hedera account IDs:

```bash
cd backend
ESCROWEYE_E2E_OWNER_WALLET=0.0.YOUR_OWNER_ACCOUNT \
ESCROWEYE_E2E_SUPPLIER_WALLET=0.0.YOUR_SUPPLIER_ACCOUNT \
.venv/bin/python -m pytest tests/test_e2e_wallet_marketplace.py -q
```

By default, local tests use dev signature mode so they can run without opening a wallet UI.

To require cryptographic wallet signatures in the backend:

```bash
ESCROWEYE_AUTH_REQUIRE_SIGNATURE=true
```

In strict mode, `/api/auth/login` verifies that `signature` signs the exact challenge `message` returned by `/api/auth/challenge` using the submitted `hedera_public_key`.

Supported verification formats:

- Ed25519 public keys as raw hex/base64 or DER.
- secp256k1 public keys as compressed/uncompressed point hex/base64 or DER.
- Signatures as hex/base64.

The automated strict-mode test uses a generated Ed25519 keypair:

```bash
cd backend
ESCROWEYE_AUTH_REQUIRE_SIGNATURE=true \
.venv/bin/python -m pytest tests/test_auth_signature_verification.py -q
```

For true user-wallet E2E, the frontend should:

1. Call `/api/auth/challenge`.
2. Ask HashPack or the connected wallet to sign the returned `message`.
3. Submit `hedera_account_id`, `hedera_public_key`, `signature`, `nonce`, and `user_type` to `/api/auth/login`.
