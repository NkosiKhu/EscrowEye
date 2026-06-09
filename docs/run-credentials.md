# EscrowEye Run Credentials

## Required for local MVP

No external credentials are required for the local MVP.

Use these defaults:

```bash
VITE_API_BASE_URL=http://localhost:8000
ESCROWEYE_AUTH_REQUIRE_SIGNATURE=false
ESCROWEYE_LOG_LEVEL=INFO
```

The local login flow accepts wallet-like Hedera account IDs such as `0.0.12345` and uses dev signatures.

## Required for strict wallet auth

```bash
ESCROWEYE_AUTH_REQUIRE_SIGNATURE=true
ESCROWEYE_SECRET=<long-random-server-secret>
```

Frontend requirement:

- Connected wallet account ID.
- Wallet public key.
- Signature over the exact `/api/auth/challenge` message.

The frontend now calls a browser wallet adapter before login. For a production
demo, expose one of these browser providers with `connect()` and `signMessage()`:

```text
window.escrowEyeWalletSigner
window.hashpack
window.HashPack
window.hederaWallet
```

The signer should return either a signature string or `{ signature, accountId,
publicKey }`. If no signer is available, the frontend uses the local dev
signature path, which only works when `ESCROWEYE_AUTH_REQUIRE_SIGNATURE=false`.

## Optional for AI validation

```bash
OPENROUTER_API_KEY=<openrouter-api-key>
OPENROUTER_MODEL=openai/gpt-4o
```

Without this, EscrowEye uses mock validation states.

## Optional for HCS events

```bash
HEDERA_OPERATOR_ID=0.0.xxxxx
HEDERA_OPERATOR_KEY=<operator-private-key>
HEDERA_HCS_TOPIC_ID=0.0.xxxxx
```

Without this, HCS events are recorded as local/mock audit events.

For production-like E2E, require real HCS submission:

```bash
HEDERA_HCS_REQUIRE_REAL=true
```

Strict mode fails fast if the operator credentials or topic ID are missing.

## Optional for IPFS proof storage

```bash
PINATA_JWT=<pinata-jwt>
PINATA_GATEWAY_URL=https://gateway.pinata.cloud
PINATA_API_URL=https://api.pinata.cloud/pinning/pinFileToIPFS
```

Without `PINATA_JWT`, proof uploads use a local deterministic CID and still
return `ipfs://<cid>` metadata while keeping a local file cache for AI review.

For production-like E2E, require real Pinata/IPFS uploads:

```bash
IPFS_REQUIRE_REAL=true
```

Strict mode fails fast if `PINATA_JWT` is missing.

## Optional for x402 payment metadata

```bash
X402_PAY_TO=0.0.xxxxx
X402_FEE_PAYER=0.0.xxxxx
X402_FACILITATOR=blocky402-mock
```

The MVP currently accepts the `X-PAYMENT` header as a paid request marker.

For production-like E2E, require facilitator verification:

```bash
X402_REQUIRE_REAL=true
X402_FACILITATOR_URL=https://your-x402-facilitator.example
X402_NETWORK=hedera:testnet
X402_ASSET=0.0.0
X402_AMOUNT=10000000
X402_MAX_TIMEOUT_SECONDS=180
```

Strict mode rejects job/service-request creation with `402
payment_verification_required` until the facilitator verifies the payment.

## Test-only wallet variables

```bash
ESCROWEYE_E2E_OWNER_WALLET=0.0.xxxxx
ESCROWEYE_E2E_SUPPLIER_WALLET=0.0.xxxxx
```

These are only used by backend E2E tests.
