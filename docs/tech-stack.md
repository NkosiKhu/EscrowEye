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
8. [Traditional vs Hedera Storage — What Lives Where](#8-traditional-vs-hedera-storage--what-lives-where)
9. [Entity Model](#9-entity-model)
10. [Auth & Session Management](#10-auth--session-management)
11. [Deployment (Hetzner VPS)](#11-deployment-hetzner-vps)
12. [Putting It All Together — EscrowEye Flow](#12-putting-it-all-together--escroweye-flow)

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
    tools=[],
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
| Job created | `{type: "job_created", job_id, owner, supplier, amount}` |
| Photo submitted | `{type: "photo_submitted", job_id, cid, supplier}` |
| Clarification requested | `{type: "clarification_requested", job_id, message, by}` |
| Clarification replied | `{type: "clarification_replied", job_id, message, by}` |
| Party confirmed | `{type: "party_confirmed", job_id, party}` |
| Escrow released | `{type: "escrow_released", job_id, tx_id, amount}` |

### Per-Job Topic Strategy

Each inspection job gets its own HCS topic. This keeps messages isolated and makes querying per-job history trivial.

### Code

```python
# Submit a message
# (via agent): submit message "{\"type\":\"photo_submitted\",\"cid\":\"bafy...\",\"job_id\":\"job_001\"}" to topic 0.0.4567

# Query messages
# (via agent): get messages from topic 0.0.4567 with limit 50
```

---

## 3. Hedera Native Multisig / Threshold Keys

**Hedera accounts natively support multisig** — no smart contract required.

### Key Concepts

- **KeyList**: All keys in the list must sign (M-of-M)
- **ThresholdKey**: N-of-M keys must sign (e.g., 2-of-3)

### Escrow Account Design

The escrow account uses a **2-of-3 ThresholdKey**:

```
Escrow Account Key = ThresholdKey(threshold=2)
  ├── Owner's Public Key
  ├── Supplier's Public Key
  └── EscrowEye Platform Key (for conflict resolution / timeout)
```

This means:
- Either party + EscrowEye can approve release (2-of-3)
- Both owner + supplier can approve without us (2-of-3)
- No single party can unilaterally move funds
- EscrowEye can step in for disputes, timeouts, or fraud detection

### Account Creation (Python SDK)

```python
from hiero_sdk_python.key_list import KeyList

threshold_key = KeyList.of(
    [owner_key, supplier_key, escroweye_platform_key],
    threshold=2
)

tx = AccountCreateTransaction() \
  .set_key(threshold_key) \
  .set_initial_balance(amount_in_tinybars) \
  .freeze_with(client)

# Two of the three keys must sign to create
tx.sign(owner_private_key)
tx.sign(escroweye_platform_key)
response = tx.execute(client)
escrow_account_id = response.get_receipt(client).account_id
```

### Release Flow

```python
tx = TransferTransaction() \
  .add_hbar_transfer(escrow_account_id, -amount) \
  .add_hbar_transfer(supplier_account_id, amount) \
  .freeze_with(client)

# Two signatures required: e.g., owner + supplier, or owner + platform
tx.sign(owner_private_key)
tx.sign(supplier_private_key)
tx.execute(client)
```

### Alternative: Multi-Sig via Scheduled Transactions

Hedera supports **scheduled transactions** — create a schedule that multiple parties sign over time. This is useful when parties sign at different times (e.g., sign via HashPack async).

```python
# Via Agent Kit scheduling params:
# "Transfer X HBAR to supplier and schedule it. Expiration: 2026-12-31"
# The SIGN_SCHEDULE_TRANSACTION_TOOL lets parties add their signatures later
```

---

## 4. Pinata IPFS

**Docs:** https://docs.pinata.cloud/files/uploading-files

Pinata is our IPFS pinning service. Photos get uploaded to IPFS, and the resulting CID is logged to HCS.

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

### Uploading Photos

```typescript
const blob = new Blob([photoBuffer], { type: "image/jpeg" });
const file = new File([blob], "inspection-photo.jpg", { type: "image/jpeg" });

const upload = await pinata.upload.public.file(file);
// → { id, name, cid: "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", ... }
```

### Client-Side Upload (Signed URLs)

For large photos, avoid proxying through the backend:

```typescript
// Backend endpoint returns a signed URL
const res = await fetch("/api/upload-url");
const { url } = await res.json();

// Client uploads directly to Pinata
const upload = await pinata.upload.public.file(file).url(url);
```

### Private IPFS (Enterprise)

Enterprise plan — files are not announced to the public IPFS network. Access via **temporary signed URLs**:

```typescript
const upload = await pinata.upload.private.file(file);
const accessUrl = await pinata.gateways.private.createAccessLink({
  cid: upload.cid,
  expires: 60,
});
```

**Important:** Private IPFS is server-side gating, not encryption. Photos should still be client-side encrypted.

---

## 5. HashPack + WalletConnect

**Docs:** https://docs.hashpack.app/dapp-developers/walletconnect

HashPack is the Hedera wallet users connect via WalletConnect. It handles key management, transaction signing, and message signing.

### Connection Flow

1. Dapp requests connection via WalletConnect
2. HashPack prompts user to approve
3. Dapp receives the user's Hedera account ID and public key
4. Dapp constructs transactions and sends them to HashPack for signing
5. HashPack returns signed transaction bytes
6. Backend submits to Hedera

### Supported Transaction Types

| Type | Used For |
|---|---|
| `Transfer` | Depositing/releasing HBAR |
| `Topic Create` | Creating per-job HCS topics |
| `Topic Submit` | Logging messages to HCS |
| `Sign Message` | Signing confirmations ("I approve this job") |
| `Smart Contract Execute` | If we go the smart contract route |

### Integration in Frontend

```typescript
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

const session = await hwc.connect();
const accountId = session.accountIds[0]; // "0.0.12345"
```

### Signing Confirmations

When a user confirms a job is complete, they sign a message that we store in HCS:

```typescript
const message = JSON.stringify({
  action: "confirm_job",
  jobId: "job_001",
  timestamp: Date.now(),
});
const signature = await hwc.signMessage(message);
```

---

## 6. x402 & Blocky402

**Docs:** https://docs.hedera.com/solutions/ai/x402#blocky402

x402 is an HTTP-native payment standard: `402 Payment Required` → client pays → server responds. Blocky402 is a **facilitator** that sponsors the HBAR network fee on behalf of the payer.

### Flow in EscrowEye

x402 gates **job creation** — the owner must pay a small HBAR fee to post a job:

```
Owner → POST /api/jobs → Server responds 402 with PaymentRequirements
     → Owner signs HBAR transfer to fee collector
     → Blocky402 verifies and submits to Hedera
     → Server creates the job
```

### Client-Side (Frontend)

```typescript
import { x402Client } from "@x402/core/client";
import { createClientHederaSigner } from "@x402/hedera";
import { ExactHederaScheme } from "@x402/hedera/exact/client";

const signer = createClientHederaSigner(
  "0.0.1111",
  privateKey,
  { network: "hedera:testnet" }
);

const client = new x402Client().register(
  "hedera:*",
  new ExactHederaScheme(signer)
);

const response = await fetch("/api/jobs", { method: "POST", body: payload });
// If 402, x402Client auto-handles the payment loop
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

> Client-side AES-256-GCM encryption before upload. The DEK (data encryption key) is encrypted for each authorized party using their Hedera public key (ECIES).

### Who Gets a Key

```
Encrypted DEK recipients:
  ├── Owner's Hedera public key
  ├── Supplier's Hedera public key
  └── EscrowEye server key (for conflict resolution / moderation)
```

EscrowEye needs a key so we can:
- Moderate photos for compliance if needed
- Decrypt for dispute resolution
- Provide access to support/admin workflows
- Enforce automated policy checks (e.g., AI moderation) on the server side

### Hybrid Encryption Scheme

```
┌──────────────────────────────────────────────────────┐
│  1. Photo is AES-256-GCM encrypted in the browser    │
│     with a random symmetric key (DEK)                │
│                                                       │
│  2. DEK is encrypted (ECIES) with each authorized     │
│     party's Hedera public key (owner, supplier, app)  │
│                                                       │
│  3. Encrypted photo → IPFS (Pinata)                  │
│     Encrypted DEKs → stored in HCS message metadata  │
│                                                       │
│  4. Any authorized party decrypts their DEK copy      │
│     using their private key, then decrypts the photo  │
└──────────────────────────────────────────────────────┘
```

### Implementation Sketch

```typescript
async function encryptPhoto(photoFile: File, authorizedPublicKeys: string[]) {
  const aesKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]
  );

  const iv = crypto.getRandomValues(new Uint8Array(12));
  const photoBuffer = await photoFile.arrayBuffer();
  const encryptedPhoto = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, aesKey, photoBuffer
  );

  const rawAesKey = await crypto.subtle.exportKey("raw", aesKey);

  const encryptedKeys = await Promise.all(
    authorizedPublicKeys.map(pubKey => encryptWithPublicKey(rawAesKey, pubKey))
  );

  const encryptedBlob = new Blob([iv, encryptedPhoto], { type: "application/octet-stream" });
  const upload = await pinata.upload.public.file(
    new File([encryptedBlob], "photo.enc")
  );

  return { cid: upload.cid, encryptedKeys, algorithm: "AES-256-GCM" };
}
```

### Key Storage (in HCS)

```json
{
  "type": "photo_submitted",
  "job_id": "job_001",
  "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra",
  "encrypted_keys": {
    "0.0.owner": "base64_encrypted_aes_key_for_owner",
    "0.0.supplier": "base64_encrypted_aes_key_for_supplier",
    "0.0.escroweye": "base64_encrypted_aes_key_for_app"
  },
  "algorithm": "AES-256-GCM"
}
```

### Libraries

- **Web Crypto API** (`crypto.subtle`) — built into browsers
- **@noble/curves** or **ecies** — for ECIES with ED25519/secp256k1
- **@hashgraph/hedera-wallet-connect** — for user key access
- **cryptography** (Python) — for server-side decryption (EscrowEye key)

---

## 8. Traditional vs Hedera Storage — What Lives Where

Not everything belongs on-ledger. Here's the split.

| Data | Store | Why |
|---|---|---|
| **User accounts** (email, profile, wallet addr) | **SQLite** | Private, frequently updated, needs indexing |
| **Jobs** (title, description, status, price, address) | **SQLite** | Needs full-text search, filtering, fast reads |
| **Job<->Supplier relationships** (bids, assignments) | **SQLite** | Relational joins, status tracking |
| **Messages / clarifications** | **SQLite** (primary) + **HCS** (audit) | Chat history in SQLite for the UI; hash + HCS for tamper-proof record |
| **Photo CIDs + encrypted DEKs** | **HCS** (immutable log) | Must be tamper-proof — links photo to job permanently |
| **Escrow account IDs + amounts** | **SQLite** (ref) + **HCS** (log) | SQLite for display; HCS for the canonical audit trail |
| **Confirmations / signatures** | **HCS** | Immutable proof of consent |
| **HBAR transactions / releases** | **HCS** | On-ledger record of every transfer |
| **Photo files** | **IPFS / Pinata** | Content-addressed storage, encrypted |

**The rule of thumb:**
- If it needs to be queried, joined, or searched → **SQLite**
- If it needs to be provably tamper-proof → **HCS**
- If it's a file → **IPFS**, with its CID in HCS

SQLite is the **source of truth for app state**. HCS is the **source of truth for audit**. They complement each other — we write to both when appropriate.

---

## 9. Entity Model

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Owner       │     │      Job         │     │  Supplier    │
│──────────────│     │──────────────────│     │──────────────│
│ id           │────>│ id               │<────│ id           │
│ email        │     │ owner_id         │     │ email        │
│ hedera_acct  │     │ title            │     │ hedera_acct  │
│ created_at   │     │ description      │     │ created_at   │
└──────────────┘     │ property_addr    │     └──────────────┘
                     │ status           │
                     │ escrow_amount    │
                     │ escrow_acct_id   │
                     │ hcs_topic_id     │
                     │ created_at       │
                     │ updated_at       │
                     └──────────────────┘
                          │        │
                          │        └──────────────────┐
                          ▼                           ▼
                     ┌──────────┐              ┌──────────────┐
                     │  Photo   │              │  Clarification │
                     │──────────│              │────────────────│
                     │ id       │              │ id             │
                     │ job_id   │              │ job_id         │
                     │ cid      │              │ from (owner/   │
                     │ enc_keys │              │      supplier) │
                     │ seq      │              │ message        │
                     └──────────┘              │ created_at     │
                                               └──────────────┘
```

### Owner Flow

1. Signs up (email + links HashPack wallet)
2. Posts a job (title, description, property address, escrow amount)
3. Funds the escrow account (HBAR via HashPack)
4. Reviews photos from supplier
5. Requests clarifications
6. Confirms job complete → releases HBAR

### Supplier Flow

1. Signs up (email + links HashPack wallet)
2. Browses available jobs
3. Selects / bids on a job
4. Submits inspection photos (encrypted → IPFS)
5. Responds to clarification requests
6. Confirms job complete → receives HBAR

---

## 10. Auth & Session Management

**Strategy:** JWT-based session management with HashPack wallet linking.

### Flow

```
1. User connects HashPack wallet → get account ID + public key
2. User signs a nonce message ("Login to EscrowEye: {nonce}")
3. Backend verifies the signature belongs to the Hedera account
4. Backend issues a JWT (stored in httpOnly cookie or localStorage)
5. JWT used for all subsequent API calls
```

### Why Both

- **JWT** gives us standard session management (roles, expiry, CSRF protection)
- **HashPack / wallet signatures** prove Hedera account ownership for high-value actions (funding, confirming, releasing)
- Low-value actions (browsing jobs, viewing profiles) require only JWT
- High-value actions (transfers, confirmations) require JWT + a fresh HashPack signature

### Implementation

```python
# POST /api/auth/login
# Body: { account_id: "0.0.12345", signature: "base64...", message: "..." }
# Backend recovers public key from signature, checks it matches account_id
# Issues JWT with { sub: user_id, account_id, role }

# POST /api/auth/wallet-challenge
# Returns a nonce for the user to sign with HashPack
```

---

## 11. Deployment (Hetzner VPS)

**Target:** Single Hetzner VPS (reasonable spec: 2-4 vCPU, 8-16 GB RAM).

### Architecture

```
Internet → Hetzner Firewall → VPS
                               ├── Caddy (reverse proxy, TLS, domain)
                               ├── Docker Compose
                               │   ├── backend (FastAPI + Uvicorn)
                               │   ├── frontend (Vite + nginx static build)
                               │   └── sqlite (mounted volume)
                               └── Cron / systemd timer (DB backup)
```

### Key Details

| Concern | Approach |
|---|---|
| **Web server** | Caddy — auto TLS, reverse proxy to backend + frontend |
| **Domain** | `escroweye.app` (or similar) |
| **Database** | SQLite file on persistent Docker volume, backed up daily |
| **Backend** | FastAPI with Uvicorn, served behind Caddy |
| **Frontend** | Built to static files, served by Caddy or nginx |
| **HBAR node** | Backend connects to Hedera testnet (dev) / mainnet (prod) |
| **Env vars** | `.env` file on server: PINATA_JWT, HEDERA keys, JWT_SECRET, etc. |
| **Backups** | `sqlite3 .backup` + `scp`/`rsync` to offsite, or Hetzner Storage Box |

### docker-compose.prod.yml

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "127.0.0.1:8000:8000"  # not public, behind Caddy
    volumes:
      - ./data:/data            # SQLite persistence
    env_file: .env
    restart: always

  frontend:
    build:
      context: ./frontend
      target: production        # multi-stage build: nginx serves static
    ports:
      - "127.0.0.1:3000:80"
    restart: always
```

### Provisioning (First Pass)

```bash
# Hetzner Ubuntu 24.04
apt update && apt install -y docker.io docker-compose-v2 caddy
git clone https://github.com/NkosiKhu/EscrowEye /opt/escroweye
cd /opt/escroweye
cp .env.example .env
# Edit .env with secrets
docker compose -f docker-compose.prod.yml up -d
```

---

## 12. Putting It All Together — EscrowEye Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         JOB LIFECYCLE                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. OWNER POSTS JOB                                                  │
│     ────────────────                                                 │
│     Owner fills job form + sets HBAR escrow amount                   │
│     → x402/Blocky402 gates with a small creation fee                │
│     → Job saved to SQLite (status: open)                            │
│     → HCS topic created, escrow account created (2-of-3 key)        │
│     → HCS: { type: "job_created", job_id, topic, escrow_account }   │
│                                                                      │
│  2. SUPPLIER SELECTS JOB                                             │
│     ─────────────────────                                            │
│     Supplier browses open jobs in UI (reads from SQLite)             │
│     → Supplier selects job → SQLite: job.status = "assigned"        │
│     → HCS: { type: "job_assigned", job_id, supplier }               │
│                                                                      │
│  3. OWNER FUNDS ESCROW                                               │
│     ────────────────────                                             │
│     Owner sends HBAR to escrow account via HashPack                  │
│     → Backend detects balance change via mirror node query           │
│     → SQLite: job.status = "funded"                                 │
│     → HCS: { type: "escrow_funded", amount }                        │
│                                                                      │
│  4. INSPECTION & PHOTOS                                              │
│     ──────────────────────                                           │
│     Supplier visits property, takes photos                           │
│     → Photos encrypted in browser (AES-256-GCM)                     │
│     → Encrypted photos uploaded to Pinata IPFS                       │
│     → Encrypted DEKs stored per party (owner, supplier, app)        │
│     → Uploaded via signed URL (server-generated, client-consumed)   │
│     → HCS: { type: "photo_submitted", cid, encrypted_keys }         │
│     → SQLite: photo record saved (cid, job_id, seq)                 │
│                                                                      │
│  5. CLARIFICATIONS                                                   │
│     ───────────────                                                   │
│     Owner requests more photos in UI                                 │
│     → SQLite: clarification saved                                   │
│     → HCS: { type: "clarification_requested", message }              │
│     → Supplier replies or submits more photos                        │
│     → HCS: { type: "clarification_replied", message }               │
│                                                                      │
│  6. BOTH CONFIRM                                                     │
│     ──────────────                                                   │
│     Owner confirms via HashPack signature                            │
│     → HCS: { type: "party_confirmed", party: "owner" }               │
│     → SQLite: owner_confirmed = true                                 │
│     Supplier confirms via HashPack signature                         │
│     → HCS: { type: "party_confirmed", party: "supplier" }            │
│     → SQLite: supplier_confirmed = true                              │
│                                                                      │
│  7. ESCROW RELEASED                                                  │
│     ─────────────────                                                 │
│     Once both confirmed, backend constructs TransferTransaction      │
│     → Owner signs via HashPack                                       │
│     → Supplier signs (or EscrowEye signs if owner+app path)         │
│     → 2-of-3 threshold met → transaction submitted to Hedera         │
│     → HBAR released to supplier's account                            │
│     → SQLite: job.status = "completed"                               │
│     → HCS: { type: "escrow_released", tx_id, amount }               │
│                                                                      │
│  8. DISPUTE (edge case)                                              │
│     ────────────────                                                  │
│     If parties can't agree, EscrowEye uses its key to arbitrate      │
│     → EscrowEye signs + one party signs → 2-of-3 reached            │
│     → Funds released per resolution                                  │
│     → HCS: { type: "dispute_resolved", resolution }                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Components & Communication

| Component | Talks To |
|---|---|
| **React Frontend** | HashPack (WalletConnect), Pinata (upload), FastAPI backend (REST/JWT) |
| **FastAPI Backend** | Hedera Agent Kit (HCS, transfers), Blocky402 (verify/settle), SQLite, Pinata (signed URLs) |
| **SQLite** | App state: users, jobs, photos, clarifications |
| **HCS** | Immutable audit log: job events, confirmations, transfers |
| **Escrow Account** | 2-of-3 threshold key account on Hedera |
| **IPFS / Pinata** | Encrypted photo storage, CIDs in HCS |
| **HashPack** | Transaction signing, message signing, key management |

---

## Decisions Made

| Question | Decision |
|---|---|
| **Escrow mechanism** | Native threshold key account (2-of-3) — simpler, gas-free, auditable |
| **Auth strategy** | JWT sessions + HashPack wallet signing (JWT for UX, HashPack for high-value actions) |
| **Deployment target** | Hetzner VPS, Docker Compose, Caddy reverse proxy |
| **Storage** | SQLite for app state, HCS for audit, IPFS for files |
| **Encryption keyholders** | Owner + Supplier + EscrowEye (for moderation/disputes) |
| **Entity model** | Owner, Supplier, Job, Photo, Clarification |

---

## Quick Dependency Summary

### Backend (Python)

```
fastapi               # REST API
uvicorn               # ASGI server
hiero-sdk-python      # Hedera SDK
hedera-agent-kit      # AI agent tools
sqlite3               # built-in, via aiosqlite or sqlmodel
python-jose           # JWT creation/verification
passlib / bcrypt      # password hashing
cryptography          # server-side ECIES decryption
httpx                 # HTTP client for Blocky402, Pinata API
python-multipart      # file uploads
```

### Frontend (TypeScript)

```
pinata                                       # IPFS uploads
@hashgraph/hedera-wallet-connect             # HashPack integration
@x402/core + @x402/hedera                    # x402 payment client
@noble/curves                                # ECIES encryption for DEKs
react-router-dom                             # routing
axios or react-query                         # API client
```
