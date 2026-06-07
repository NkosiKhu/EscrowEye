# EscrowEye — REST API Reference

> For the frontend dev. All endpoints are prefixed with `/api`.  
> Auth is JWT in `Authorization: Bearer <token>` header.  
> All request/response bodies are JSON unless noted.

---

## Auth

### `POST /api/auth/challenge`

Get a nonce to sign with HashPack.

**Request:**
```json
{ "account_id": "0.0.12345" }
```

**Response:**
```json
{ "nonce": "a1b2c3d4", "message": "Sign this message to login to EscrowEye: a1b2c3d4" }
```

---

### `POST /api/auth/login`

Verify the wallet signature and issue a JWT.

**Request:**
```json
{
  "account_id": "0.0.12345",
  "signature": "base64_encoded_signature",
  "nonce": "a1b2c3d4",
  "user_type": "owner"          // "owner" | "supplier"
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "email": "alice@example.com",
    "user_type": "owner",
    "account_id": "0.0.12345"
  }
}
```

---

### `GET /api/auth/me`

Get current user profile.

**Response:**
```json
{
  "id": 1,
  "email": "alice@example.com",
  "user_type": "owner",
  "account_id": "0.0.12345",
  "hedera_pub_key": "302a300506032b6570032100..."
}
```

---

### `PATCH /api/auth/profile`

Update profile (email, etc).

**Request:**
```json
{ "email": "newemail@example.com" }
```

**Response:**
```json
{ "id": 1, "email": "newemail@example.com" }
```

---

## Homes

### `GET /api/homes`

List all homes owned by the current user.

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

### `GET /api/homes/:id`

Get home with rooms.

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

### `PUT /api/homes/:id`

Update home.

**Request:**
```json
{ "name": "My Updated House", "address": "123 New St" }
```

**Response:**
```json
{ "id": 1, "name": "My Updated House", "address": "123 New St" }
```

---

### `DELETE /api/homes/:id`

Delete home and its rooms.

**Response:** `204 No Content`

---

### `POST /api/homes/:id/rooms`

Add a room to a home.

**Request:**
```json
{ "name": "Bathroom", "sq_meters": 12 }
```

**Response:**
```json
{ "id": 3, "name": "Bathroom", "sq_meters": 12 }
```

---

### `DELETE /api/homes/:id/rooms/:room_id`

Remove a room.

**Response:** `204 No Content`

---

## Jobs

### `GET /api/jobs`

List jobs. Filter varies by user type.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `status` | string | Filter by status: `bidding`, `awarded`, `funded`, `in_progress`, `awaiting_confirmation`, `completed`, `disputed` |
| `role` | string | `"owned"` — jobs I posted (owner), `"assigned"` — jobs I'm working on (supplier) |

**Response:**
```json
{
  "jobs": [
    {
      "id": 1,
      "title": "Clean my beach house",
      "description": "Deep clean after party",
      "suggested_price": 50000000,
      "status": "bidding",
      "home": { "id": 1, "name": "My Beach House", "address": "42 Ocean Drive" },
      "owner": { "id": 1, "account_id": "0.0.12345" },
      "supplier": null,
      "bid_count": 3,
      "lowest_bid": 45000000,
      "created_at": "2026-06-07T10:00:00Z"
    }
  ]
}
```

---

### `POST /api/jobs`

Create a new job.

**Request:**
```json
{
  "home_id": 1,
  "title": "Clean my beach house",
  "description": "Deep clean after party",
  "suggested_price": 50000000,
  "instructions": "Focus on kitchen and windows",
  "available_times": "Any weekday after 2pm"
}
```

**Notes:**
- Requires x402 creation fee payment first (see creation-fee endpoints).
- The `creation_fee_paid` flag must be true or the endpoint rejects.

**Response:**
```json
{
  "id": 1,
  "status": "bidding",
  "creation_fee_paid": false
}
```

---

### `GET /api/jobs/:id`

Get full job details.

**Response:**
```json
{
  "id": 1,
  "title": "Clean my beach house",
  "description": "Deep clean after party",
  "suggested_price": 50000000,
  "instructions": "Focus on kitchen and windows",
  "available_times": "Any weekday after 2pm",
  "status": "funded",
  "home": { "id": 1, "name": "My Beach House", "address": "42 Ocean Drive" },
  "owner": { "id": 1, "account_id": "0.0.12345" },
  "supplier": { "id": 2, "account_id": "0.0.67890" },
  "escrow_account": "0.0.99999",
  "hcs_topic": "0.0.88888",
  "accepted_bid": { "id": 5, "amount": 48000000 },
  "created_at": "2026-06-07T10:00:00Z",
  "updated_at": "2026-06-07T14:00:00Z"
}
```

---

### `POST /api/jobs/:id/award`

Owner accepts a bid and assigns the supplier.

**Request:**
```json
{ "bid_id": 5 }
```

**Response:**
```json
{
  "job_id": 1,
  "status": "awarded",
  "supplier": { "id": 2, "account_id": "0.0.67890" }
}
```

---

### `POST /api/jobs/:id/confirm`

Sign to confirm job completion.

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

When both parties have confirmed, escrow releases automatically.

---

### `POST /api/jobs/:id/dispute`

Either party can dispute.

**Request:**
```json
{ "reason": "Photos don't match scope of work" }
```

**Response:**
```json
{ "job_id": 1, "status": "disputed" }
```

---

## Bids

### `GET /api/jobs/:id/bids`

List all bids for a job.

**Response:**
```json
{
  "bids": [
    {
      "id": 5,
      "supplier": { "id": 2, "account_id": "0.0.67890" },
      "amount": 48000000,
      "message": "I can do it Thursday morning",
      "status": "pending",
      "created_at": "2026-06-07T11:00:00Z"
    }
  ]
}
```

---

### `POST /api/jobs/:id/bids`

Place a bid on a job.

**Request:**
```json
{
  "amount": 48000000,
  "message": "I can do it Thursday morning"
}
```

**Response:**
```json
{
  "id": 5,
  "amount": 48000000,
  "status": "pending"
}
```

---

### `PUT /api/bids/:id`

Update your bid (before it's accepted).

**Request:**
```json
{ "amount": 45000000, "message": "I can do it for less" }
```

**Response:**
```json
{ "id": 5, "amount": 45000000, "status": "pending" }
```

---

### `DELETE /api/bids/:id`

Withdraw your bid.

**Response:** `204 No Content`

---

## Messages (Conversational UI)

### `GET /api/jobs/:id/messages`

Get all messages for a job, newest last.

**Response:**
```json
{
  "messages": [
    {
      "id": 10,
      "sender": { "id": 2, "account_id": "0.0.67890", "user_type": "supplier" },
      "body": "Here are the before photos",
      "photo_ids": [1, 2, 3],
      "photos": [
        { "id": 1, "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", "sequence": 1 },
        { "id": 2, "cid": "bafybeig6v5a...", "sequence": 2 }
      ],
      "created_at": "2026-06-07T15:00:00Z"
    }
  ]
}
```

---

### `POST /api/jobs/:id/messages`

Send a message, optionally with photos.

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
  "id": 11,
  "body": "Here are the before photos",
  "photo_ids": [1, 2, 3],
  "created_at": "2026-06-07T15:00:00Z"
}
```

---

## Photos

### `POST /api/jobs/:id/photos`

Upload photos directly (multipart, backend proxies to Pinata).

**Request:** `multipart/form-data`

| Field | Type |
|---|---|
| `photos` | File[] (one or more image files) |
| `room_id` | int (optional) |
| `encrypted_keys` | string (JSON — see tech-stack.md) |

**Response:**
```json
{
  "photos": [
    { "id": 1, "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra", "sequence": 1 }
  ]
}
```

---

### `GET /api/jobs/:id/photos`

List all photos for a job.

**Response:**
```json
{
  "photos": [
    {
      "id": 1,
      "cid": "bafybeihgxdzljxb26q6nf3r3eifqeedsvt2eubqtskghpme66cgjyw4fra",
      "room": { "id": 1, "name": "Kitchen" },
      "uploaded_by": { "id": 2, "account_id": "0.0.67890" },
      "sequence": 1,
      "created_at": "2026-06-07T15:00:00Z"
    }
  ]
}
```

---

## x402 / Creation Fee

### `POST /api/jobs/creation-fee`

Get the x402 payment requirements to create a job. Call this before `POST /api/jobs`.

**Response:**
```json
{
  "payment_requirements": {
    "scheme": "exact",
    "network": "hedera:testnet",
    "amount": "10000000",
    "asset": "0.0.0",
    "payTo": "0.0.7162784",
    "maxTimeoutSeconds": 180,
    "extra": { "feePayer": "0.0.7162784" }
  }
}
```

The frontend uses this to construct the x402 payment via Blocky402. After successful payment, call the next endpoint:

### `POST /api/jobs/creation-fee/callback`

Called by the frontend after x402 settlement succeeds.

**Request:**
```json
{
  "transaction_id": "0.0.7162784@1700000000.000000000"
}
```

**Response:**
```json
{ "fee_paid": true, "fee_token": "temp_token_for_job_creation" }
```

Include `fee_token` in the subsequent `POST /api/jobs` request.

---

## Escrow

### `POST /api/jobs/:id/fund`

Owner funds the escrow account after a bid is accepted.

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
  "escrow_account": "0.0.99999",
  "amount": 48000000
}
```

---

## Health

### `GET /api/health`

**Response:**
```json
{ "status": "healthy" }
```

---

## Summary Table

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/challenge` | No | Get nonce for wallet signing |
| POST | `/api/auth/login` | No | Verify signature, get JWT |
| GET | `/api/auth/me` | Yes | Current user profile |
| PATCH | `/api/auth/profile` | Yes | Update profile |
| GET | `/api/homes` | Yes | List my homes |
| POST | `/api/homes` | Yes | Create home |
| GET | `/api/homes/:id` | Yes | Home details + rooms |
| PUT | `/api/homes/:id` | Yes | Update home |
| DELETE | `/api/homes/:id` | Yes | Delete home |
| POST | `/api/homes/:id/rooms` | Yes | Add room |
| DELETE | `/api/homes/:id/rooms/:rid` | Yes | Remove room |
| GET | `/api/jobs` | Yes | List jobs (filtered) |
| POST | `/api/jobs` | Yes | Create job (needs fee_token) |
| GET | `/api/jobs/:id` | Yes | Job details |
| POST | `/api/jobs/:id/award` | Yes | Accept a bid |
| POST | `/api/jobs/:id/confirm` | Yes | Sign confirmation |
| POST | `/api/jobs/:id/dispute` | Yes | Dispute job |
| GET | `/api/jobs/:id/bids` | Yes | List bids |
| POST | `/api/jobs/:id/bids` | Yes | Place bid |
| PUT | `/api/bids/:id` | Yes | Update bid |
| DELETE | `/api/bids/:id` | Yes | Withdraw bid |
| GET | `/api/jobs/:id/messages` | Yes | Get conversation |
| POST | `/api/jobs/:id/messages` | Yes | Send message |
| POST | `/api/jobs/:id/photos` | Yes | Upload photos (multipart) |
| GET | `/api/jobs/:id/photos` | Yes | List photos |
| POST | `/api/jobs/creation-fee` | Yes | Get x402 payment requirements |
| POST | `/api/jobs/creation-fee/callback` | Yes | Confirm fee paid |
| POST | `/api/jobs/:id/fund` | Yes | Fund escrow |
| GET | `/api/health` | No | Health check |
