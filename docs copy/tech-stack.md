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
| `core_consensus_plugin` | `CREATE_TOPIC_TOOL`, `SUBMIT_TOPIC_MESSAGE_TOOL` | Create per-job topics and log the three audit events |
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

### Agent Model Runtime: OpenRouter

Hedera Agent Kit provides the Hedera tools. LangGraph orchestrates the agent state. OpenRouter provides the LLM runtime for both assistant and photo-review calls.

Use `langchain-openrouter` and `ChatOpenRouter` instead of `ChatOpenAI` with a custom `base_url`.

```python
from langchain_openrouter import ChatOpenRouter

llm = ChatOpenRouter(
    model="openai/gpt-4o",
    temperature=0,
)
```

Why this route:
- `openai/gpt-4o` supports the multimodal photo-review path.
- OpenRouter accepts image inputs through its chat completions-compatible API. Raw OpenRouter calls use an `image_url` content part with a URL or `data:image/jpeg;base64,...` value.
- In this project, LangGraph calls the model through `ChatOpenRouter`, so reviewer images should be sent as LangChain `HumanMessage` content blocks with `{"type": "image", "base64": image_data, "mime_type": "image/jpeg"}`.
- `ChatOpenRouter` supports LangGraph usage patterns including tracing, structured output, tool calling, multimodal inputs, and provider routing.

---

## 2. Hedera Consensus Service (HCS)

HCS is our **audit anchor** — not a replica of app state. Only 3 events get written to HCS.

### What We'll Log (exactly)

| Event | HCS Message Content | When |
|---|---|---|
| `job_created` | `{type: "job_created", job_id, owner, suggested_price_tinybar}` | Owner posts a job after x402 payment |
| `job_completed` | `{type: "job_completed", job_id, tx_hash}` | Escrow released |
| `job_disputed` | `{type: "job_disputed", job_id}` | Either party disputes |

Everything else (messages, bids, photo metadata, encrypted key envelopes) lives in **SQLite**. Photo bytes live in **IPFS/Pinata**.

### Per-Job Topic Strategy

Each job gets its own HCS topic. This keeps audit events isolated and makes per-job audit history easy to query.

### Code

```python
# Submit an audit event
# (via agent): submit message "{\"type\":\"job_created\",\"job_id\":1,\"owner\":\"0.0.12345\",\"suggested_price_tinybar\":5000000000}" to topic 0.0.4567

# Query audit events
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

Pinata is our IPFS pinning service. Photos get uploaded to IPFS, and the resulting CID is stored in SQLite with the job's photo metadata. CIDs are not mirrored to HCS in the MVP.

### SDK Setup

```bash
npm install pinata-web3
```

```typescript
import { PinataSDK } from "pinata-web3";

const pinata = new PinataSDK({
  pinataJwt: process.env.PINATA_JWT!,
  pinataGateway: "example-gateway.mypinata.cloud",
});
```

### Uploading Photos

```typescript
const blob = new Blob([photoBuffer], { type: "image/jpeg" });
const file = new File([blob], "inspection-photo.jpg", { type: "image/jpeg" });

const upload = await pinata.upload.file(file);
// → { id, name, cid: "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", ... }
```

### MVP Upload Path

For the hackathon MVP, the frontend sends photos to the backend and the backend proxies to Pinata:

```typescript
const form = new FormData();
form.append("photos", file);
form.append("encrypted_keys", JSON.stringify(encryptedKeys));

const res = await fetch(`/api/jobs/${jobId}/photos`, {
  method: "POST",
  body: form,
});
```

Signed direct uploads can be added later if large files become a bottleneck.

### Private IPFS (Enterprise)

Enterprise plan — files are not announced to the public IPFS network. Access via **temporary signed URLs**:

```typescript
// Exact API depends on the Pinata private-files product tier.
// Keep this server-side and return short-lived access links only.
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
| `Topic Submit` | Logging audit events to HCS |
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

When a user confirms a job is complete, they sign a message that the backend verifies and stores with the job confirmation record. HCS only receives the final `job_completed` audit event after escrow release.

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
     → Frontend replays POST /api/jobs with the payment header
     → Server creates the job and writes job_created to HCS
```

There are no `/api/jobs/creation-fee` or callback endpoints in the canonical API. `POST /api/jobs` owns the full `402 → pay → replay → create` loop.

### Client-Side (Frontend)

```typescript
import { x402Client } from "@x402/core/client";
import { ExactHederaScheme } from "@x402/hedera/exact/client";

// App wrapper around the x402 Hedera signer + HashPack/WalletConnect.
// The browser never receives or stores the user's private key.
const signer = await createHashPackX402Signer({
  hederaAccountId,
  walletConnectSession,
  network: "hedera:testnet",
});

const client = new x402Client().register(
  "hedera:*",
  new ExactHederaScheme(signer)
);

const response = await client.fetch("/api/jobs", { method: "POST", body: payload });
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
│     Encrypted DEKs → stored in SQLite photo metadata │
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
  const upload = await pinata.upload.file(
    new File([encryptedBlob], "photo.enc")
  );

  return { cid: upload.cid, encryptedKeys, algorithm: "AES-256-GCM" };
}
```

### Key Storage (SQLite photo metadata)

```json
{
  "job_id": "job_001",
  "photo_id": 1,
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

Not everything belongs on-ledger. HCS is lightweight — it only stores **critical state transitions** (proof a job was created, completed, paid out). Everything else lives in SQLite.

| Data | Store | Why |
|---|---|---|
| **User accounts** (email, profile, wallet addr) | **SQLite** | Private, frequently updated, needs indexing |
| **Jobs** (title, description, status, price, address) | **SQLite** | Needs full-text search, filtering, fast reads |
| **Bids** | **SQLite** | Relational joins, supplier queries, owner comparison |
| **Messages / clarifications** | **SQLite** | Conversational UI — needs fast reads/writes, no on-chain benefit |
| **Photo CIDs + encrypted DEKs** | **SQLite** (reference) + **IPFS** (blob) | CIDs stored in SQLite alongside jobs; IPFS for the actual bytes |
| **Photo files** | **IPFS / Pinata** | Content-addressed storage, encrypted client-side |
| **Escrow account IDs + amounts** | **SQLite** | App state; the on-ledger balance is the real source of truth |
| **Job created event** | **HCS** | Immutable proof of creation |
| **Job completed event** | **HCS** | Immutable proof of successful payout |
| **Job disputed event** | **HCS** | Immutable proof of dispute |
| **HBAR transaction hash** | **HCS** | Links on-ledger payout to the job record |

**The split:**

- **SQLite** — source of truth for app state (users, jobs, bids, messages, photos, everything the UI touches)
- **HCS** — tamper-proof seal on exactly 3 events: `job_created`, `job_completed` (with tx hash), `job_disputed`
- **IPFS** — encrypted photo blobs, nothing else

No double-writes. No "write to SQLite AND HCS for messages." HCS is strictly the audit anchor, not a replica of app state.

---

## 9. Entity Model

### Schema

```sql
-- Both owners and suppliers are Users, differentiated by user_type
CREATE TABLE users (
    id              INTEGER PRIMARY KEY,
    email           TEXT UNIQUE,
    user_type       TEXT NOT NULL CHECK(user_type IN ('owner', 'supplier')),
    hedera_account_id TEXT UNIQUE NOT NULL,  -- "0.0.12345"
    hedera_public_key TEXT NOT NULL,         -- ED25519 or secp256k1 public key
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE homes (
    id              INTEGER PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES users(id),
    name            TEXT NOT NULL,  -- "My Beach House"
    address         TEXT NOT NULL,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rooms (
    id              INTEGER PRIMARY KEY,
    home_id         INTEGER NOT NULL REFERENCES homes(id),
    name            TEXT NOT NULL,  -- "Kitchen", "Master Bedroom"
    sq_meters       REAL
);

CREATE TABLE jobs (
    id                  INTEGER PRIMARY KEY,
    owner_id            INTEGER NOT NULL REFERENCES users(id),
    home_id             INTEGER NOT NULL REFERENCES homes(id),
    supplier_id         INTEGER REFERENCES users(id),
    title               TEXT NOT NULL,
    description         TEXT,
    suggested_price_tinybar INTEGER,    -- in tinybars, for display only
    access_notes        TEXT,           -- "Gate code: 1234, key under mat"
    available_times     TEXT,           -- free-text for MVP
    status              TEXT NOT NULL DEFAULT 'bidding'
                        CHECK(status IN (
                            'bidding', 'awarded', 'funded', 'in_progress',
                            'awaiting_confirmation', 'completed', 'disputed'
                        )),
    escrow_account_id   TEXT,           -- "0.0.escrow"
    hcs_topic_id        TEXT,           -- "0.0.topic"
    creation_fee_paid   INTEGER DEFAULT 0,
    release_tx_hash     TEXT,           -- on release
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bids (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES jobs(id),
    supplier_id     INTEGER NOT NULL REFERENCES users(id),
    amount_tinybar  INTEGER NOT NULL,
    message         TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'accepted', 'declined', 'withdrawn')),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES jobs(id),
    sender_user_id  INTEGER REFERENCES users(id), -- null for agent/system
    sender_type     TEXT NOT NULL DEFAULT 'human'
                    CHECK(sender_type IN ('human', 'agent', 'system')),
    body            TEXT NOT NULL,
    photo_ids       TEXT,               -- JSON array of photo PKs: "[1, 2, 3]"
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE photos (
    id              INTEGER PRIMARY KEY,
    job_id          INTEGER NOT NULL REFERENCES jobs(id),
    room_id         INTEGER REFERENCES rooms(id),
    uploaded_by_user_id INTEGER NOT NULL REFERENCES users(id),
    cid             TEXT NOT NULL,       -- IPFS content hash
    encrypted_keys_json TEXT NOT NULL,   -- JSON: {"0.0.owner": "b64...", "0.0.supplier": "b64...", "0.0.app": "b64..."}
    sequence        INTEGER NOT NULL,
    review_status   TEXT NOT NULL DEFAULT 'pending'
                    CHECK(review_status IN ('pending', 'passed', 'failed', 'needs_retake')),
    review_notes    TEXT,
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Status Flow

```
bidding → awarded → funded → in_progress → awaiting_confirmation → completed
                                                                        ↕
                                                                    disputed
```

1. **bidding** — Owner posted job (creation fee paid via x402). Suppliers place bids.
2. **awarded** — Owner accepted a bid → supplier is assigned.
3. **funded** — Owner paid bid amount into the 2-of-3 escrow account.
4. **in_progress** — Supplier does the work, uploads photos, messages flow.
5. **awaiting_confirmation** — All photos submitted, waiting on owner sign-off.
6. **completed** — Both parties confirmed → HBAR released to supplier.
7. **disputed** — Either party hit the dispute button → simple toggle.

### Owner Flow

1. Signs up + links HashPack → wallet linked
2. Creates home (name, address, rooms)
3. Posts job (selects home, adds description + suggested price)
4. Pays ~£10 creation fee via x402
5. Views bids on job page → accepts one
6. Pays bid amount into escrow via HashPack
7. Reviews photos + messages in conversational UI
8. Confirms completion → HBAR released to supplier

### Supplier Flow

1. Signs up + links HashPack → wallet linked
2. Browses open jobs (bidding status)
3. Places bid (`amount_tinybar` + optional message)
4. Gets notified on acceptance → job moves to funded after owner pays
5. Does the work, uploads photos (encrypted → IPFS)
6. Messages back and forth in conversational UI
7. Confirms completion → receives HBAR

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

### Agent-Friendly API

The REST API *is* the agent interface. Same routes, same JSON schemas.

```
POST /api/jobs              # Owner creates job — agent can do this too
GET  /api/jobs              # List available jobs with filters
POST /api/jobs/{job_id}/bids       # Supplier places bid
POST /api/jobs/{job_id}/award      # Owner accepts bid
POST /api/jobs/{job_id}/fund       # Owner funds escrow
POST /api/jobs/{job_id}/mark-ready # Supplier marks ready
POST /api/jobs/{job_id}/messages   # Send message
GET  /api/jobs/{job_id}/messages   # Get conversation
POST /api/jobs/{job_id}/confirm    # Sign confirmation
POST /api/jobs/{job_id}/dispute    # Trigger dispute
```

An agent acting on behalf of a user authenticates with the same JWT and calls the same endpoints. For the hackathon, agents operate within an authenticated app session — no separate agent auth flow. Wallet-required steps remain UI-mediated: the agent can prepare `POST /api/jobs`, `fund`, or `confirm`, but HashPack/x402 signing happens in the frontend.

### Implementation

```python
# POST /api/auth/login
# Body: { hedera_account_id: "0.0.12345", hedera_public_key: "...", signature: "base64...", nonce: "..." }
# Backend verifies the signature and account ownership
# Issues JWT with { sub: user_id, hedera_account_id, role }

# POST /api/auth/challenge
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
| **Env vars** | `.env` file on server: OPENROUTER_API_KEY, PINATA_JWT, HEDERA keys, JWT_SECRET, etc. |
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
│     Owner fills job form (home, description, suggested_price_tinybar)│
│     → x402/Blocky402 gates with ~£10 flat creation fee              │
│     → Job saved to SQLite (status: bidding)                         │
│     → HCS: { type: "job_created", job_id }                          │
│                                                                      │
│  2. SUPPLIERS BID                                                    │
│     ───────────────                                                   │
│     Suppliers browse open jobs → place bids (amount_tinybar + msg)   │
│     → SQLite: bids saved, visible to all on job page                │
│     → Owner sees bids, picks one                                    │
│     → bid.status = accepted, job.status = awarded                   │
│     → supplier_id set on job                                        │
│                                                                      │
│  3. OWNER FUNDS ESCROW                                               │
│     ────────────────────                                             │
│     Owner pays accepted bid amount into 2-of-3 escrow account        │
│     → via HashPack signature                                        │
│     → Escrow account created (2-of-3: owner + supplier + app)       │
│     → HBAR transferred in                                            │
│     → SQLite: job.status = funded, escrow_account_id saved          │
│                                                                      │
│  4. INSPECTION & PHOTOS                                              │
│     ──────────────────────                                           │
│     Supplier does the work, takes photos                             │
│     → Photos encrypted in browser (AES-256-GCM)                     │
│     → Encrypted photos uploaded to Pinata IPFS (via signed URL)     │
│     → Encrypted DEKs for owner + supplier + app                     │
│     → SQLite: photo records saved (cid, job_id, seq)               │
│     → Photos attached to messages via photo_ids JSON array          │
│     → SQLite: job.status = in_progress                               │
│                                                                      │
│  5. CONVERSATIONAL UI                                                │
│     ───────────────────                                               │
│     Owner reviews photos, sends messages                             │
│     → Supplier replies, uploads more photos                          │
│     → All stored in SQLite messages + photos tables                 │
│     → No HCS writes for chat                                        │
│                                                                      │
│  6. BOTH CONFIRM                                                     │
│     ──────────────                                                   │
│     Supplier clicks "Done" → job.status = awaiting_confirmation     │
│     Owner reviews in conversational UI                              │
│     → Owner clicks "Confirm" (HashPack signature)                   │
│     → Both signatures collected                                     │
│     → 2-of-3 threshold met → TransferTransaction submitted           │
│     → HBAR released to supplier                                     │
│     → SQLite: job.status = completed                                 │
│     → HCS: { type: "job_completed", job_id, tx_hash }               │
│                                                                      │
│  7. DISPUTE                                                          │
│     ────────                                                        │
│     Either party clicks "Dispute"                                    │
│     → SQLite: job.status = disputed                                  │
│     → HCS: { type: "job_disputed", job_id }                         │
│     → EscrowEye can arbitrate using its 2-of-3 key                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Components & Communication

| Component | Talks To |
|---|---|
| **React Frontend** | HashPack (WalletConnect), Pinata (upload), FastAPI backend (REST/JWT) |
| **FastAPI Backend** | Hedera Agent Kit (HCS, transfers), Blocky402 (verify/settle), SQLite, Pinata (signed URLs) |
| **SQLite** | App state: users, homes, rooms, jobs, bids, messages, photos |
| **HCS** | Exactly 3 events: job_created, job_completed, job_disputed |
| **Escrow Account** | 2-of-3 threshold key account on Hedera |
| **IPFS / Pinata** | Encrypted photo storage, CIDs referenced in SQLite |
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
| **Entity model** | User (owner/supplier), Home, Room, Job, Bid, Message (photo_ids as JSON), Photo |
| **Agent interface** | Same REST API as the web UI — agents use the same endpoints with a JWT |
| **HCS scope** | Exactly 3 events: job_created, job_completed (with tx hash), job_disputed |
| **Creation fee** | ~£10 flat x402 fee paid by owner when posting a job |
| **Bidding** | Open bids visible to all suppliers; owner picks one |

---

## Quick Dependency Summary

### Frontend

#### UI

```bash
npm install tailwindcss @tailwindcss/vite
npx shadcn@latest init
```

`shadcn/ui` pulls in the usual UI utilities as needed, including `lucide-react`, `class-variance-authority`, `clsx`, `tailwind-merge`, and animation helpers.

#### API & State

```bash
npm install @tanstack/react-query @tanstack/react-query-devtools axios
```

#### Forms

```bash
npm install react-hook-form @hookform/resolvers zod
```

#### Routing

```bash
npm install react-router-dom
```

#### Utilities

```bash
npm install react-dropzone date-fns sonner
```

#### Wallet / Crypto

```bash
npm install @hashgraph/hedera-wallet-connect @hashgraph/sdk
npm install @x402/core @x402/hedera
npm install @noble/curves pinata-web3
```

### Backend

#### API

```bash
pip install fastapi "uvicorn[standard]" python-multipart httpx "python-jose[cryptography]"
```

#### Database

```bash
pip install "sqlalchemy[asyncio]" aiosqlite alembic pydantic-settings
```

#### Security

```bash
pip install "passlib[bcrypt]" cryptography
```

#### Agent / AI

```bash
pip install langgraph langchain-core langchain-openrouter Pillow
```

Use `ChatOpenRouter` from `langchain-openrouter` with `model="openai/gpt-4o"` for the multimodal reviewer. Resize images with Pillow before base64 encoding.

#### Hedera

```bash
pip install hiero-sdk-python hedera-agent-kit
```

#### Dev

```bash
pip install python-dotenv pytest pytest-asyncio httpx loguru
```
