# EscrowEye — REST API Reference

> Canonical REST contract for the frontend, backend, and agent tools.
> All endpoints are prefixed with `/api`.
> Auth is JWT in the `Authorization: Bearer <token>` header unless noted.
> All request/response bodies are JSON unless noted.

---

## Conventions

- Path parameters use `{name}` in this document, for example `/api/jobs/{job_id}`.
- Hedera wallet fields are named `hedera_account_id` and `hedera_public_key`.
- HBAR amounts are always integer tinybars and use `_tinybar` suffixes.
- Human messages are always stored before any agent response is generated.
- `sender_user_id` is nullable so `agent` and `system` messages do not require a human sender.
- x402 gates `POST /api/jobs` directly. There is no separate creation-fee preflight or callback endpoint.

---

## Auth

### `POST /api/auth/challenge`

Get a nonce to sign with HashPack.

**Auth:** No

**Request:**
```json
{
  "hedera_account_id": "0.0.12345"
}
```

**Response:**
```json
{
  "nonce": "a1b2c3d4",
  "message": "Sign this message to login to EscrowEye: a1b2c3d4"
}
```

---

### `POST /api/auth/login`

Verify the wallet signature and issue a JWT.

**Auth:** No

**Request:**
```json
{
  "hedera_account_id": "0.0.12345",
  "hedera_public_key": "302a300506032b6570032100...",
  "signature": "base64_encoded_signature",
  "nonce": "a1b2c3d4",
  "user_type": "owner"
}
```

`user_type` is `"owner"` or `"supplier"`.

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "email": "alice@example.com",
    "user_type": "owner",
    "hedera_account_id": "0.0.12345",
    "hedera_public_key": "302a300506032b6570032100..."
  }
}
```

---

### `GET /api/auth/me`

Get the current user profile.

**Auth:** Yes

**Response:**
```json
{
  "id": 1,
  "email": "alice@example.com",
  "user_type": "owner",
  "hedera_account_id": "0.0.12345",
  "hedera_public_key": "302a300506032b6570032100..."
}
```

---

### `PATCH /api/auth/profile`

Update profile fields that are not wallet-derived.

**Auth:** Yes

**Request:**
```json
{
  "email": "newemail@example.com"
}
```

**Response:**
```json
{
  "id": 1,
  "email": "newemail@example.com"
}
```

---

## Homes

### `GET /api/homes`

List all homes owned by the current user.

**Auth:** Yes

**Response:**
```json
{
  "homes": [
    {
      "id": 1,
      "name": "My Beach House",
      "address": "42 Ocean Drive, Miami FL",
      "rooms": [
        { "id": 1, "name": "Kitchen", "sq_meters": 20 },
        { "id": 2, "name": "Living Room", "sq_meters": 35 }
      ]
    }
  ]
}
```

---

### `POST /api/homes`

Create a new home.

**Auth:** Yes

**Request:**
```json
{
  "name": "My Beach House",
  "address": "42 Ocean Drive, Miami FL"
}
```

**Response:**
```json
{
  "id": 1,
  "name": "My Beach House",
  "address": "42 Ocean Drive, Miami FL",
  "rooms": []
}
```

---

### `GET /api/homes/{home_id}`

Get a home with its rooms.

**Auth:** Yes

**Response:**
```json
{
  "id": 1,
  "name": "My Beach House",
  "address": "42 Ocean Drive, Miami FL",
  "rooms": [
    { "id": 1, "name": "Kitchen", "sq_meters": 20 }
  ]
}
```

---

### `PUT /api/homes/{home_id}`

Update a home.

**Auth:** Yes

**Request:**
```json
{
  "name": "My Updated House",
  "address": "123 New St"
}
```

**Response:**
```json
{
  "id": 1,
  "name": "My Updated House",
  "address": "123 New St"
}
```

---

### `DELETE /api/homes/{home_id}`

Delete a home and its rooms.

**Auth:** Yes

**Response:** `204 No Content`

---

### `POST /api/homes/{home_id}/rooms`

Add a room to a home.

**Auth:** Yes

**Request:**
```json
{
  "name": "Bathroom",
  "sq_meters": 12
}
```

**Response:**
```json
{
  "id": 3,
  "name": "Bathroom",
  "sq_meters": 12
}
```

---

### `DELETE /api/homes/{home_id}/rooms/{room_id}`

Remove a room.

**Auth:** Yes

**Response:** `204 No Content`

---

## Jobs

### `GET /api/jobs`

List jobs. Filters vary by user type.

**Auth:** Yes

**Query params:**

| Param | Type | Description |
|---|---|---|
| `status` | string | Filter by status: `bidding`, `awarded`, `funded`, `in_progress`, `awaiting_confirmation`, `completed`, `disputed` |
| `role` | string | `"owned"` for jobs posted by the current user, `"assigned"` for jobs assigned to the current supplier |

**Response:**
```json
{
  "jobs": [
    {
      "id": 1,
      "title": "Clean my beach house",
      "description": "Deep clean after party",
      "suggested_price_tinybar": 5000000000,
      "status": "bidding",
      "home": { "id": 1, "name": "My Beach House", "address": "42 Ocean Drive" },
      "owner": { "id": 1, "hedera_account_id": "0.0.12345" },
      "supplier": null,
      "bid_count": 3,
      "lowest_bid_tinybar": 4500000000,
      "created_at": "2026-06-07T10:00:00Z"
    }
  ]
}
```

---

### `POST /api/jobs`

Create a new job. This endpoint is x402-gated.

**Auth:** Yes

**Request:**
```json
{
  "home_id": 1,
  "title": "Clean my beach house",
  "description": "Deep clean after party",
  "suggested_price_tinybar": 5000000000,
  "access_notes": "Gate code: 1234, key under mat",
  "available_times": "Any weekday after 2pm"
}
```

**Unpaid response:** `402 Payment Required`

```json
{
  "error": "payment_required",
  "payment_requirements": {
    "scheme": "exact",
    "network": "hedera:testnet",
    "amount": "10000000",
    "asset": "0.0.0",
    "payTo": "0.0.7162784",
    "maxTimeoutSeconds": 180,
    "extra": {
      "feePayer": "0.0.7162784"
    }
  }
}
```

The frontend x402 client pays through Blocky402, then replays the same `POST /api/jobs` request with the payment header.

**Paid response:** `201 Created`

```json
{
  "id": 1,
  "status": "bidding",
  "creation_fee_paid": true,
  "hcs_topic_id": "0.0.88888"
}
```

Side effects:
- A job row is written to SQLite.
- A per-job HCS topic is created.
- A `job_created` audit event is submitted to HCS.
- If the request originated from the chat panel, the agent posts a confirmation message.

---

### `GET /api/jobs/{job_id}`

Get full job details.

**Auth:** Yes

**Response:**
```json
{
  "id": 1,
  "title": "Clean my beach house",
  "description": "Deep clean after party",
  "suggested_price_tinybar": 5000000000,
  "access_notes": "Gate code: 1234, key under mat",
  "available_times": "Any weekday after 2pm",
  "status": "funded",
  "home": { "id": 1, "name": "My Beach House", "address": "42 Ocean Drive" },
  "owner": { "id": 1, "hedera_account_id": "0.0.12345" },
  "supplier": { "id": 2, "hedera_account_id": "0.0.67890" },
  "escrow_account_id": "0.0.99999",
  "hcs_topic_id": "0.0.88888",
  "accepted_bid": { "id": 5, "amount_tinybar": 4800000000 },
  "creation_fee_paid": true,
  "created_at": "2026-06-07T10:00:00Z",
  "updated_at": "2026-06-07T14:00:00Z"
}
```

---

### `POST /api/jobs/{job_id}/award`

Owner accepts a bid and assigns the supplier.

**Auth:** Yes

**Request:**
```json
{
  "bid_id": 5
}
```

**Response:**
```json
{
  "job_id": 1,
  "status": "awarded",
  "supplier": { "id": 2, "hedera_account_id": "0.0.67890" }
}
```

---

### `POST /api/jobs/{job_id}/fund`

Owner funds the escrow account after a bid is accepted.

**Auth:** Yes

**Request:**
```json
{
  "signed_transaction": "base64_encoded_transaction_bytes_from_hashpack"
}
```

**Response:**
```json
{
  "job_id": 1,
  "status": "funded",
  "escrow_account_id": "0.0.99999",
  "amount_tinybar": 4800000000
}
```

---

### `POST /api/jobs/{job_id}/mark-ready`

Supplier marks the job ready for owner confirmation.

**Auth:** Yes

**Request:**
```json
{
  "message": "All rooms are complete and photos are uploaded."
}
```

**Response:**
```json
{
  "job_id": 1,
  "status": "awaiting_confirmation"
}
```

---

### `POST /api/jobs/{job_id}/confirm`

Sign to confirm job completion.

**Auth:** Yes

**Request:**
```json
{
  "signature": "base64_signature_from_hashpack",
  "message": "{\"action\":\"confirm_job\",\"job_id\":1,\"timestamp\":1717776000000}"
}
```

**Response:**
```json
{
  "job_id": 1,
  "status": "completed",
  "tx_hash": "0.0.12345@1717776000.000000000"
}
```

When the required confirmation signatures are collected, escrow releases automatically and a `job_completed` audit event is submitted to HCS.

---

### `POST /api/jobs/{job_id}/dispute`

Either party can dispute a job.

**Auth:** Yes

**Request:**
```json
{
  "reason": "Photos do not match the scope of work."
}
```

**Response:**
```json
{
  "job_id": 1,
  "status": "disputed"
}
```

Side effect: a `job_disputed` audit event is submitted to HCS.

---

## Bids

### `GET /api/jobs/{job_id}/bids`

List all bids for a job.

**Auth:** Yes

**Response:**
```json
{
  "bids": [
    {
      "id": 5,
      "supplier": { "id": 2, "hedera_account_id": "0.0.67890" },
      "amount_tinybar": 4800000000,
      "message": "I can do it Thursday morning",
      "status": "pending",
      "created_at": "2026-06-07T11:00:00Z"
    }
  ]
}
```

---

### `POST /api/jobs/{job_id}/bids`

Place a bid on a job.

**Auth:** Yes

**Request:**
```json
{
  "amount_tinybar": 4800000000,
  "message": "I can do it Thursday morning"
}
```

**Response:**
```json
{
  "id": 5,
  "amount_tinybar": 4800000000,
  "status": "pending"
}
```

---

### `PUT /api/bids/{bid_id}`

Update your bid before it is accepted.

**Auth:** Yes

**Request:**
```json
{
  "amount_tinybar": 4500000000,
  "message": "I can do it for less."
}
```

**Response:**
```json
{
  "id": 5,
  "amount_tinybar": 4500000000,
  "status": "pending"
}
```

---

### `DELETE /api/bids/{bid_id}`

Withdraw your bid.

**Auth:** Yes

**Response:** `204 No Content`

---

## Messages

### `GET /api/jobs/{job_id}/messages`

Get all messages for a job, newest last.

**Auth:** Yes

**Response:**
```json
{
  "messages": [
    {
      "id": 10,
      "sender_user_id": 2,
      "sender": {
        "id": 2,
        "hedera_account_id": "0.0.67890",
        "user_type": "supplier"
      },
      "sender_type": "human",
      "body": "Here are the before photos",
      "photo_ids": [1, 2, 3],
      "photos": [
        { "id": 1, "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", "sequence": 1 },
        { "id": 2, "cid": "bafybeig6v5a...", "sequence": 2 }
      ],
      "created_at": "2026-06-07T15:00:00Z"
    },
    {
      "id": 11,
      "sender_user_id": null,
      "sender": null,
      "sender_type": "agent",
      "body": "Kitchen photos look good. Bathroom still needs a retake.",
      "photo_ids": [],
      "photos": [],
      "created_at": "2026-06-07T15:01:00Z"
    }
  ]
}
```

---

### `POST /api/jobs/{job_id}/messages`

Send a human message, optionally with photos.

**Auth:** Yes

**Request:**
```json
{
  "body": "Here are the before photos",
  "photo_ids": [1, 2, 3]
}
```

**Response:**
```json
{
  "id": 10,
  "sender_user_id": 2,
  "sender_type": "human",
  "body": "Here are the before photos",
  "photo_ids": [1, 2, 3],
  "created_at": "2026-06-07T15:00:00Z"
}
```

Trigger behavior:
- If `photo_ids` is non-empty, the photo review agent runs in the background.
- If `photo_ids` is empty and the chat panel is in agent mode, the assistant agent runs after the human message is stored.
- Agent and system messages are inserted by server-side services, not directly by normal clients.

---

## Photos

### `POST /api/jobs/{job_id}/photos`

Upload photos directly. For the hackathon MVP, the backend proxies uploads to Pinata.

**Auth:** Yes

**Request:** `multipart/form-data`

| Field | Type |
|---|---|
| `photos` | File[] |
| `room_id` | int, optional |
| `encrypted_keys` | stringified JSON |

**Response:**
```json
{
  "photos": [
    {
      "id": 1,
      "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra",
      "sequence": 1,
      "review_status": "pending"
    }
  ]
}
```

---

### `GET /api/jobs/{job_id}/photos`

List all photos for a job.

**Auth:** Yes

**Response:**
```json
{
  "photos": [
    {
      "id": 1,
      "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra",
      "room": { "id": 1, "name": "Kitchen" },
      "uploaded_by": { "id": 2, "hedera_account_id": "0.0.67890" },
      "sequence": 1,
      "review_status": "passed",
      "created_at": "2026-06-07T15:00:00Z"
    }
  ]
}
```

---

### `PATCH /api/jobs/{job_id}/photos/{photo_id}`

Associate a photo with a room and update review metadata. This is primarily used by the photo review agent.

**Auth:** Yes

**Request:**
```json
{
  "room_id": 1,
  "review_status": "passed",
  "review_notes": "Kitchen counters and floor look clean."
}
```

`review_status` is `"pending"`, `"passed"`, `"failed"`, or `"needs_retake"`.

**Response:**
```json
{
  "id": 1,
  "job_id": 1,
  "room": { "id": 1, "name": "Kitchen" },
  "review_status": "passed",
  "review_notes": "Kitchen counters and floor look clean."
}
```

---

## Audit Events

### `GET /api/jobs/{job_id}/audit-events`

Read the canonical HCS audit events for a job.

**Auth:** Yes

**Response:**
```json
{
  "hcs_topic_id": "0.0.88888",
  "events": [
    {
      "type": "job_created",
      "job_id": 1,
      "sequence_number": 1,
      "consensus_timestamp": "2026-06-07T10:00:01.000000000Z"
    },
    {
      "type": "job_completed",
      "job_id": 1,
      "tx_hash": "0.0.12345@1717776000.000000000",
      "sequence_number": 2,
      "consensus_timestamp": "2026-06-07T16:00:01.000000000Z"
    }
  ]
}
```

Only these event types are written to HCS in the MVP:
- `job_created`
- `job_completed`
- `job_disputed`

Messages, bids, photos, and photo CIDs live in SQLite/IPFS and are not mirrored to HCS.

---

## Health

### `GET /api/health`

**Auth:** No

**Response:**
```json
{
  "status": "healthy"
}
```

---

## Summary Table

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/challenge` | No | Get nonce for wallet signing |
| POST | `/api/auth/login` | No | Verify signature and issue JWT |
| GET | `/api/auth/me` | Yes | Current user profile |
| PATCH | `/api/auth/profile` | Yes | Update profile |
| GET | `/api/homes` | Yes | List my homes |
| POST | `/api/homes` | Yes | Create home |
| GET | `/api/homes/{home_id}` | Yes | Home details and rooms |
| PUT | `/api/homes/{home_id}` | Yes | Update home |
| DELETE | `/api/homes/{home_id}` | Yes | Delete home |
| POST | `/api/homes/{home_id}/rooms` | Yes | Add room |
| DELETE | `/api/homes/{home_id}/rooms/{room_id}` | Yes | Remove room |
| GET | `/api/jobs` | Yes | List jobs |
| POST | `/api/jobs` | Yes + x402 | Create job |
| GET | `/api/jobs/{job_id}` | Yes | Job details |
| POST | `/api/jobs/{job_id}/award` | Yes | Accept a bid |
| POST | `/api/jobs/{job_id}/fund` | Yes | Fund escrow |
| POST | `/api/jobs/{job_id}/mark-ready` | Yes | Supplier marks ready |
| POST | `/api/jobs/{job_id}/confirm` | Yes | Confirm completion |
| POST | `/api/jobs/{job_id}/dispute` | Yes | Dispute job |
| GET | `/api/jobs/{job_id}/bids` | Yes | List bids |
| POST | `/api/jobs/{job_id}/bids` | Yes | Place bid |
| PUT | `/api/bids/{bid_id}` | Yes | Update bid |
| DELETE | `/api/bids/{bid_id}` | Yes | Withdraw bid |
| GET | `/api/jobs/{job_id}/messages` | Yes | Get conversation |
| POST | `/api/jobs/{job_id}/messages` | Yes | Send message |
| POST | `/api/jobs/{job_id}/photos` | Yes | Upload photos |
| GET | `/api/jobs/{job_id}/photos` | Yes | List photos |
| PATCH | `/api/jobs/{job_id}/photos/{photo_id}` | Yes | Associate/review photo |
| GET | `/api/jobs/{job_id}/audit-events` | Yes | Read HCS audit events |
| GET | `/api/health` | No | Health check |
