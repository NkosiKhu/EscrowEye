# EscrowEye — Tech Stack Reference

> A deep dive into each technology we're using, what it does, how it fits EscrowEye, and code snippets to get started.

---

## Table of Contents

1. [Hedera Agent Kit (Python)](#1-hedera-agent-kit-python)
2. [Hedera Consensus Service (HCS)](#2-hedera-consensus-service-hcs)
3. [Hedera Native Multisig / Threshold Keys](#3-hedera-native-multisig--threshold-keys)
4. [Pinata IPFS](#4-pinata-ipfs)
5. [HashPack + WalletConnect](#5-hashpack--walletconnect)
6. [x402 & Blocky402](#6-x402--blocky402)
7. [Encryption Strategy for Photos](#7-encryption-strategy-for-photos)
8. [Putting It All Together — EscrowEye Flow](#8-putting-it-all-together--escroweye-flow)

---

## 1. Hedera Agent Kit (Python)

**Repo:** https://github.com/hashgraph/hedera-agent-kit-py

The Python SDK gives us a suite of **plugins** that map directly to Hedera services. Each plugin exposes tools that our backend (or an AI agent) can call.

### Relevant Plugins for EscrowEye

| Plugin | Tools We'll Use | Why |
|---|---|---|
| `core_account_plugin` | `TRANSFER_HBAR_TOOL`, `CREATE_ACCOUNT_TOOL`, `GET_HBAR_BALANCE_QUERY_TOOL` | Deposit/Release HBAR, create escrow accounts |
| `core_consensus_plugin` | `CREATE_TOPIC_TOOL`, `SUBMIT_TOPIC_MESSAGE_TOOL` | Log job state, photo CIDs, confirmations to HCS |
| `core_consensus_query_plugin` | `GET_TOPIC_MESSAGES_QUERY_TOOL` | Fetch job history / audit trail |
| `core_token_plugin` | `ASSOCIATE_TOKEN_TOOL` | Associate HTS tokens if needed |
| `core_misc_query_plugin` | `GET_EXCHANGE_RATE_TOOL` | HBAR → fiat conversions |

### Minimal Setup

```python
from hiero_sdk_python import Client, Network, AccountId, PrivateKey
from hedera_agent_kit import Configuration, Context, AgentMode
from hedera_agent_kit.langchain.toolkit import HederaLangchainToolkit
from hedera_agent_kit.plugins import (
    core_account_plugin,
    core_consensus_plugin,
    core_consensus_query_plugin,
)

client = Client(Network("testnet"))
operator_id = AccountId.from_string("0.0.12345")
operator_key = PrivateKey.from_string("302e020100300506032b657004220420...")
client.set_operator(operator_id, operator_key)

configuration = Configuration(
    tools=[],  # empty = load all tools from selected plugins
    context=Context(mode=AgentMode.AUTONOMOUS, account_id=str(operator_id)),
    plugins=[
        core_account_plugin,
        core_consensus_plugin,
        core_consensus_query_plugin,
    ],
)

toolkit = HederaLangchainToolkit(client, configuration)
tools = toolkit.get_tools()
```

### Hooks & Policies (v3.4.0+)

The kit provides a **7-stage tool lifecycle** where hooks and policies can execute at 4 points:

```
[Pre-Tool Execution]       → Hook Stage 1
[Parameter Normalization]
[Post-Parameter Normalization] → Hook Stage 2
[Core Action]
[Post-Core Action]          → Hook Stage 3
[Secondary Action]
[Post-Tool Execution]       → Hook Stage 4
```

**Policies** can *block* execution (e.g., "don't transfer more than 100 HBAR"). **Hooks** *observe* (e.g., log every transfer).

We can use policies to:
- Enforce max escrow deposit amounts
- Block transfers before both parties confirm
- Require HCS message submission before releasing funds

---

## 2. Hedera Consensus Service (HCS)

HCS is our **audit log**. Every event in a job lifecycle gets written as a message to a HCS topic.

### What We'll Log

| Event | HCS Message Content |
|---|---|
| Job created | `{type: "job_created", job_id, requester, inspector, amount}` |
| Photo submitted | `{type: "photo_submitted", job_id, cid, inspector}` |
| Clarification requested | `{type: "clarification_requested", job_id, message}` |
| Clarification replied | `{type: "clarification_replied", job_id, message}` |
| Party confirmed | `{type: "party_confirmed", job_id, party}` |
| Escrow released | `{type: "escrow_released", job_id, tx_id, amount}` |

### Per-Job Topic Strategy

Each inspection job gets its own HCS topic. This keeps messages isolated and makes querying per-job history trivial.

### Code

```python
from hedera_agent_kit.plugins import core_consensus_plugin, core_consensus_query_plugin

# Create a topic for a new job
topic_tool = core_consensus_plugin.SUBMIT_TOPIC_MESSAGE_TOOL

# Submit a message
submit_tool = core_consensus_plugin.SUBMIT_TOPIC_MESSAGE_TOOL
# (via agent): submit message "{\"type\":\"photo_submitted\",\"cid\":\"bafy...\",\"job_id\":\"job_001\"}" to topic 0.0.4567

# Query messages
query_tool = core_consensus_query_plugin.GET_TOPIC_MESSAGES_QUERY_TOOL
# (via agent): get messages from topic 0.0.4567 with limit 50
```

---

## 3. Hedera Native Multisig / Threshold Keys

**Hedera accounts natively support multisig** — no smart contract required. This is a critical architectural decision.

### Key Concepts

- **KeyList**: All keys in the list must sign (M-of-M)
- **ThresholdKey**: N-of-M keys must sign (e.g., 2-of-3)

### Escrow Account Design

For EscrowEye, the escrow account uses a **2-of-2 ThresholdKey**:

```
Escrow Account Key = ThresholdKey(threshold=2)
  ├── Requester's Public Key
  └── Inspector's Public Key
```

This means:
- Neither party can unilaterally move funds
- Both must sign to release HBAR to the inspector
- Hedera enforces this at the consensus level — no contract code to audit

### Code (Python SDK)

```python
from hiero_sdk_python import PrivateKey, PublicKey
from hiero_sdk_python.account.account_create_transaction import AccountCreateTransaction
from hiero_sdk_python.response_code import ResponseCode

# Generate or obtain keys
requester_key = PublicKey.from_string(requester_public_key_str)
inspector_key = PublicKey.from_string(inspector_public_key_str)

# Create a 2-of-2 threshold key
from hiero_sdk_python.key_list import KeyList
threshold_key = KeyList.of(
    [requester_key, inspector_key],
    threshold=2
)

# Create the escrow account
tx = AccountCreateTransaction()
  .set_key(threshold_key)
  .set_initial_balance(amount_in_tinybars)
  .freeze_with(client)

# Both parties sign
tx.sign(requester_private_key)
tx.sign(inspector_private_key)
response = tx.execute(client)
escrow_account_id = response.get_receipt(client).account_id
```

### Releasing Funds (Both Must Sign)

```python
from hiero_sdk_python.account.transfer_transaction import TransferTransaction

tx = TransferTransaction()
  .add_hbar_transfer(escrow_account_id, -amount)
  .add_hbar_transfer(inspector_account_id, amount)
  .freeze_with(client)

# Both parties sign the same frozen transaction
tx.sign(requester_private_key)
tx.sign(inspector_private_key)
tx.execute(client)
```

### Alternative: Multi-Sig via Scheduled Transactions

Hedera also supports **scheduled transactions** — create a schedule that multiple parties sign over time:

```python
# Via Agent Kit scheduling params:
# "Transfer X HBAR to inspector and schedule it. Expiration: 2026-12-31"
```

This is useful if parties sign at different times (e.g., sign via HashPack, come back later).

---

## 4. Pinata IPFS

**Docs:** https://docs.pinata.cloud/files/uploading-files

Pinata is our IPFS pinning service. Photos get uploaded to IPFS, and the resulting CID (content-addressed hash) is logged to HCS.

### SDK Setup

```bash
npm install pinata
```

```typescript
import { PinataSDK } from "pinata";

const pinata = new PinataSDK({
  pinataJwt: process.env.PINATA_JWT!,
  pinataGateway: "example-gateway.mypinata.cloud",
});
```

### Uploading Photos (Server-Side)

```typescript
// From a buffer (e.g., after receiving multipart upload in FastAPI)
const blob = new Blob([photoBuffer], { type: "image/jpeg" });
const file = new File([blob], "inspection-photo.jpg", { type: "image/jpeg" });

// Upload to public IPFS
const upload = await pinata.upload.public.file(file);
// → { id, name, cid: "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", ... }

// Log CID to HCS
console.log(`Photo CID: ${upload.cid}`);
```

### Client-Side Upload (Signed URLs)

For large photos, avoid proxying through our backend:

```typescript
// Backend endpoint returns a signed URL
const res = await fetch("/api/upload-url");
const { url } = await res.json();

// Client uploads directly to Pinata
const upload = await pinata.upload.public.file(file).url(url);
```

### Private IPFS (Enterprise)

Pinata offers **Private IPFS** (Enterprise plan) where files are not announced to the public IPFS network. Access is via **temporary signed URLs** that expire:

```typescript
// Upload private
const upload = await pinata.upload.private.file(file);

// Generate access link (expires in 60 seconds)
const accessUrl = await pinata.gateways.private.createAccessLink({
  cid: upload.cid,
  expires: 60,
});
```

**Important:** Private IPFS gates access at the server level (signed URLs), but files themselves are not encrypted. See [Encryption Strategy](#7-encryption-strategy-for-photos) for true end-to-end encryption.

### Metadata & Key-Values

```typescript
const upload = await pinata.upload.public
  .file(file)
  .name("kitchen-sink.jpg")
  .keyvalues({
    jobId: "job_001",
    inspectorId: "0.0.789",
    propertyId: "prop_42",
  });
```

---

## 5. HashPack + WalletConnect

**Docs:** https://docs.hashpack.app/dapp-developers/walletconnect

HashPack is the Hedera wallet our users connect via WalletConnect. It handles key management and transaction signing.

### Connection Flow

1. Dapp requests connection via WalletConnect
2. HashPack prompts user to approve
3. Dapp receives the user's Hedera account ID and public key
4. Dapp constructs transactions, sends them to HashPack for signing
5. HashPack returns signed transaction bytes
6. Dapp (or backend) submits to Hedera

### Supported Transaction Types (EscrowEye-relevant)

| Type | Used For |
|---|---|
| `Transfer` | Depositing/releasing HBAR |
| `Topic Create` | Creating per-job HCS topics |
| `Topic Submit` | Logging messages to HCS |
| `Sign Message` | Signing arbitrary data (e.g., "I confirm this job") |
| `Smart Contract Execute` | If we go the smart contract route |

### Integration in Frontend

```typescript
// Using @hashgraph/hedera-wallet-connect
import { HederaWalletConnect } from "@hashgraph/hedera-wallet-connect";

const hwc = new HederaWalletConnect({
  projectId: "your_walletconnect_project_id",
  metadata: {
    name: "EscrowEye",
    description: "Property Inspection Escrow",
    url: "https://escroweye.app",
    icons: ["https://escroweye.app/icon.png"],
  },
});

// Connect
const session = await hwc.connect();
const accountId = session.accountIds[0]; // "0.0.12345"

// Sign a transfer transaction
const txBytes = await hwc.signTransaction(transferTransaction);
// Submit to Hedera via backend
```

### Signing Confirmations

When a user confirms a job is complete, they sign a message:

```typescript
const message = JSON.stringify({
  action: "confirm_job",
  jobId: "job_001",
  timestamp: Date.now(),
});
const signature = await hwc.signMessage(message);
// Store signature + message to HCS as proof
```

---

## 6. x402 & Blocky402

**Docs:** https://docs.hedera.com/solutions/ai/x402#blocky402

x402 is an HTTP-native payment standard: `402 Payment Required` → client pays → server responds. Blocky402 is a **facilitator** that sponsors the network fee.

### Flow in EscrowEye

x402 gates **job creation** — the requester must pay a small HBAR fee to create a job:

```
Requester → POST /api/jobs → Server responds 402 with payment requirements
         → Requester signs HBAR transfer to fee collector
         → Blocky402 verifies and submits to Hedera
         → Server creates the job
```

### Client-Side (in our frontend or agent)

```typescript
import { x402Client } from "@x402/core/client";
import { createClientHederaSigner } from "@x402/hedera";
import { ExactHederaScheme } from "@x402/hedera/exact/client";
import { PrivateKey } from "@hiero-ledger/sdk";

const signer = createClientHederaSigner(
  "0.0.1111",
  PrivateKey.fromString(process.env.HEDERA_PRIVATE_KEY!),
  { network: "hedera:testnet" }
);

const client = new x402Client().register(
  "hedera:*",
  new ExactHederaScheme(signer)
);

// When we get a 402 response, the client auto-signs and retries
const response = await fetch("/api/jobs", { method: "POST", body: payload });
// If 402, x402Client handles the payment loop automatically
```

### Server-Side (our FastAPI backend)

```python
# The resource server checks payment via Blocky402
# POST the PaymentPayload to https://api.testnet.blocky402.com/verify
# POST to https://api.testnet.blocky402.com/settle
```

### Blocky402 Details

| Property | Value |
|---|---|
| Testnet facilitator | `https://api.testnet.blocky402.com` |
| Fee payer account | `0.0.7162784` |
| Discovery | `GET /supported` |
| Verify | `POST /verify` |
| Settle | `POST /settle` |

---

## 7. Encryption Strategy for Photos

> **Question:** Can we upload encrypted photos that only the app, User A's key, or User B's key can decrypt?

**Yes, with client-side encryption before upload.** Pinata's Private IPFS gated access (signed URLs) is a server-side access control — Pinata can still see the files. For true end-to-end encryption where only designated parties can decrypt, we do this:

### Hybrid Encryption Scheme (PGP-style)

```
┌─────────────────────────────────────────────────────┐
│  1. Photo is AES-256-GCM encrypted on the client    │
│     with a random symmetric key (DEK)               │
│                                                      │
│  2. The DEK is encrypted with each authorized        │
│     party's Hedera public key (ECIES)               │
│                                                      │
│  3. Encrypted photo → IPFS (via Pinata)            │
│     Encrypted DEKs → stored in HCS message metadata │
│                                                      │
│  4. Authorized party decrypts their DEK copy        │
│     using their private key (via HashPack),          │
│     then decrypts the photo                          │
└─────────────────────────────────────────────────────┘
```

### Why This Works for EscrowEye

- **Inspector uploads a photo** — the browser encrypts it before it leaves the device
- **Requester views the photo** — the app fetches the encrypted CIP from IPFS, decrypts the DEK using the requester's HashPack-signed key, then decrypts the photo
- **Neither Pinata nor our backend** ever sees unencrypted photo data
- **The app can also have a key** to enforce compliance checks (e.g., AI moderation) before encryption

### Implementation Sketch

```typescript
// Client-side encryption (browser)
async function encryptPhoto(photoFile: File, authorizedPublicKeys: string[]) {
  // 1. Generate random AES-256-GCM key
  const aesKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"]
  );

  // 2. Encrypt the photo
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const photoBuffer = await photoFile.arrayBuffer();
  const encryptedPhoto = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    aesKey,
    photoBuffer
  );

  // 3. Export AES key as raw bytes
  const rawAesKey = await crypto.subtle.exportKey("raw", aesKey);

  // 4. Encrypt AES key for each authorized party using ECIES
  //    (using Hedera secp256k1 or ED25519 public keys)
  const encryptedKeys = await Promise.all(
    authorizedPublicKeys.map(pubKey => encryptWithPublicKey(rawAesKey, pubKey))
  );

  // 5. Upload encrypted photo to IPFS
  const encryptedBlob = new Blob([iv, encryptedPhoto], { type: "application/octet-stream" });
  const upload = await pinata.upload.public.file(
    new File([encryptedBlob], "photo.enc")
  );

  return {
    cid: upload.cid,
    encryptedKeys, // one per authorized party
    algorithm: "AES-256-GCM",
  };
}
```

### Key Storage

The encrypted DEKs (one per authorized party) are logged to HCS alongside the CID:

```json
{
  "type": "photo_submitted",
  "job_id": "job_001",
  "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra",
  "encrypted_keys": {
    "0.0.1234": "base64_encrypted_aes_key_for_requester",
    "0.0.5678": "base64_encrypted_aes_key_for_inspector"
  },
  "algorithm": "AES-256-GCM"
}
```

### Libraries

- **Web Crypto API** (`crypto.subtle`) — built into browsers, no extra deps
- **@noble/curves** or **ecies** — for ECIES encryption with ED25519/secp256k1 keys
- **@hashgraph/hedera-wallet-connect** — to sign/derive keys for decrypting

---

## 8. Putting It All Together — EscrowEye Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                         JOB LIFECYCLE                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. CREATE JOB                                                    │
│     ────────────                                                  │
│     Requester calls POST /api/jobs                                │
│     → x402/Blocky402 gates with HBAR payment                     │
│     → Backend creates HCS topic for this job                     │
│     → Backend creates escrow account (2-of-2 threshold key)      │
│     → HCS: { type: "job_created", job_id, escrow_account }       │
│                                                                   │
│  2. FUND ESCROW                                                   │
│     ─────────────                                                 │
│     Requester sends HBAR to escrow account via HashPack           │
│     → HCS: { type: "escrow_funded", amount }                     │
│                                                                   │
│  3. INSPECT & SUBMIT PHOTOS                                       │
│     ──────────────────────────                                    │
│     Inspector uploads photos via frontend                         │
│     → Photos encrypted client-side (AES-256-GCM)                  │
│     → Encrypted photos uploaded to Pinata IPFS                    │
│     → Encrypted DEKs stored per authorized party                  │
│     → HCS: { type: "photo_submitted", cid, encrypted_keys }      │
│                                                                   │
│  4. BACK-AND-FORTH                                                │
│     ────────────────                                               │
│     Requester requests clarifications                             │
│     → HCS: { type: "clarification_requested", message }           │
│     Inspector replies / submits more photos                       │
│     → HCS: { type: "clarification_replied", message }            │
│     → HCS: { type: "photo_submitted", cid }                      │
│                                                                   │
│  5. CONFIRM                                                        │
│     ────────                                                      │
│     Both parties sign a confirmation message via HashPack          │
│     → HCS: { type: "party_confirmed", party: "requester" }        │
│     → HCS: { type: "party_confirmed", party: "inspector" }        │
│                                                                   │
│  6. RELEASE                                                        │
│     ────────                                                      │
│     Backend constructs TransferTransaction from escrow account     │
│     → Requester signs via HashPack                                │
│     → Inspector signs via HashPack                                │
│     → Both signatures → submitted to Hedera                       │
│     → HBAR released to inspector                                  │
│     → HCS: { type: "escrow_released", tx_id }                     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### Which Components Talk to What

| Component | Talks To |
|---|---|
| **React Frontend** | HashPack (via WalletConnect), Pinata (client uploads), FastAPI backend |
| **FastAPI Backend** | Hedera Agent Kit (HCS, transfers), Blocky402 (verify/settle), Pinata (signed URLs) |
| **AI Agent** | Hedera Agent Kit tools (autonomous mode for policy checks) |
| **HCS** | Immutable audit log for every job |
| **Escrow Account** | 2-of-2 threshold key account on Hedera |
| **IPFS / Pinata** | Encrypted photo storage, CIDs referenced from HCS |

---

## Open Questions We Still Need to Decide

| Question | Options | Notes |
|---|---|---|
| **Escrow mechanism** | Threshold key account (native) vs Smart Contract | Threshold key is simpler, no gas, no contract audit. Smart contract is more programmable (timeouts, partial releases). |
| **Auth strategy** | HashPack WalletConnect only, or also server-side JWTs? | WalletConnect gives us native Hedera signing. JWTs could enable session management. |
| **Deployment target** | VPS, Railway, K8s, Hedera ecosystem? | Affects docker-compose, CI/CD, domain setup. |

---

## Quick Dependency Summary

### Backend (Python)

```
fastapi
uvicorn
hiero-sdk-python
hedera-agent-kit      # pip install hedera-agent-kit
```

### Frontend (TypeScript)

```
pinata                 # IPFS uploads
@hashgraph/hedera-wallet-connect  # HashPack integration
@x402/core             # x402 payment client
@x402/hedera           # Hedera exact scheme
@noble/curves          # ECIES encryption for photo DEKs
```
