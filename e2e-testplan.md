# EscrowEye — Live E2E Test Plan

**Date:** 2026-06-09  
**Mode:** Testnet (HEDERA_NETWORK=testnet) — real Hedera transactions  
**Funding:** Mode 2 — server-side (DEV_OWNER_PRIVATE_KEY), no wallet required  
**Progress log:** `/Users/nkosinathikhumalo/EscrowEye/live-e2e.md`

---

## Environment Checklist

| Item | Value | Status |
|------|-------|--------|
| `HEDERA_NETWORK` | `testnet` | ✅ root `.env` |
| `HEDERA_OPERATOR_ID` | `0.0.8600977` | ✅ root `.env` |
| `HEDERA_OPERATOR_PRIVATE_KEY` | `[see .env]` | ✅ root `.env` |
| `HEDERA_OPERATOR_ID` | `0.0.8600977` | ✅ root `.env` |
| `DEV_OWNER_ID` | `0.0.9160905` | ✅ root `.env` |
| `DEV_OWNER_PRIVATE_KEY` | `[see .env]` | ✅ root `.env` |
| `DEV_SUPPLIER_ID` | `0.0.9160906` | ✅ root `.env` |
| `DEV_SUPPLIER_PRIVATE_KEY` | `[see .env]` | ✅ root `.env` |
| `VITE_API_BASE_URL` | `http://localhost:5103` | ✅ `frontend/.env.local` |
| `VITE_WALLET_ENABLED` | `false` | ✅ `frontend/.env.local` — server funds |
| Backend port | `5103` | start with `uvicorn` |
| Frontend port | `5173` | start with `npx vite` |

---

## Test Images

| File | Room label | Path |
|------|-----------|------|
| `cleanbathroom.jpg` | Bathroom | `/Users/nkosinathikhumalo/EscrowEye/testimages/cleanbathroom.jpg` |
| `cleanlivingroom.jpeg` | Living Room | `/Users/nkosinathikhumalo/EscrowEye/testimages/cleanlivingroom.jpeg` |
| `clean-bedroom.webp` | Bedroom | `/Users/nkosinathikhumalo/EscrowEye/testimages/clean-bedroom.webp` |

---

## Test Accounts

| Role | Hedera ID | Keys |
|------|-----------|------|
| Owner | `0.0.9160905` | private + public key in root `.env` |
| Supplier | `0.0.9160906` | private + public key in root `.env` |

---

## Server Start Commands

```bash
# Terminal 1 — Backend
cd /Users/nkosinathikhumalo/EscrowEye/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 5103

# Terminal 2 — Frontend
cd /Users/nkosinathikhumalo/EscrowEye/frontend
npx vite --port 5173
```

---

## Phase 0 — Pre-flight

**Actions:**
1. Confirm both servers are running and reachable
2. `GET http://localhost:5103/api/health` (or `/docs`) returns 200
3. `http://localhost:5173` loads the Onboarding screen

**Log to `live-e2e.md`:** ✅/❌ + any errors

---

## Phase 1 — Owner: Login & Create Service Request

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. Navigate to `http://localhost:5173`
2. Select role **Owner**
3. Enter:
   - First name: `Nkosi`, Last name: `Khumalo`
   - Hedera account: `0.0.9160905`
   - Public key: `302d300706052b8104000a03220003ab24aaa0cbe543902fec1a19ebf686381d1699a712bfc9e9a2ca48012691cc98`
4. Click **Create desktop workspace** → should land on Browse view
5. Click a worker (e.g. Chijioke Nwosu) → click **Request quote**
6. Fill in the request modal:
   - Need: `Full home clean — bathroom, bedroom, and living room. Upload proof per room.`
   - Schedule: pick any time slot
   - Budget: `2` HBAR
7. Click through to **Summary** and submit
8. Navigate to **My Requests** in the sidebar

**Expected outcomes:**
- Notice bar shows `Request #N created with x402 payment.`
- Job appears in My Requests list with status `quote_requested`
- Backend log shows `service_request.created`

**Log to `live-e2e.md`:** `request_id`, status, notice text

---

## Phase 2 — Supplier: Login & Send Quote

**Actors:** Supplier (`0.0.9160906`)

**Steps:**
1. Sign out (Sidebar → Sign out)
2. Select role **Supplier**
3. Enter:
   - First name: `Dev`, Last name: `Supplier`
   - Hedera account: `0.0.9160906`
   - Public key: `302d300706052b8104000a032200033bf7cec97de73a306b6f2ccaf9b7c5674850604e3fa29dfc952b17e0b04f5319`
4. Click **Create desktop workspace** → lands on Jobs → Offers
5. Find the request posted by the owner in the offers list, click it
6. Click **Send quote** → enter `1.5` HBAR → submit

**Expected outcomes:**
- Notice shows `Quote sent.`
- Job appears in active jobs sidebar
- Backend log shows `quote.created`

**Log to `live-e2e.md`:** `quote_id`, amount, status

---

## Phase 3 — Owner: Accept Quote → Hedera Escrow Created

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. Sign out, log back in as **Owner** (same credentials as Phase 1)
2. Go to **My Requests** → select the job
3. In the detail panel, the **Incoming quotes** section should show:
   - `1.5 HBAR — Quote submitted from supplier desktop flow.`
   - **Accept quote** button
4. Click **Accept quote**

**Expected outcomes:**
- Notice: `Quote accepted. Hedera escrow account created.`
- Job status changes to `quote_accepted`
- `escrow_account_id` field populates with a real Hedera account ID (e.g. `0.0.XXXXXX`)
- Backend log: `escrow.account_created request_id=N escrow_id=0.0.XXXXXX`
- **Hashscan check:** `https://hashscan.io/testnet/account/0.0.XXXXXX` — account exists with 0 HBAR balance

**Log to `live-e2e.md`:** `escrow_account_id`, Hashscan link, screenshot

---

## Phase 4 — Owner: Fund Escrow

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. (Stay on the same job detail view)
2. After accepting the quote, the **Fund escrow (1.5 HBAR)** button should appear
3. Click **Fund escrow (1.5 HBAR)**
4. Button transitions: `idle` → `signing` → `done` (Mode 2: server handles it all)

**Expected outcomes:**
- Notice: `Escrow funded on Hedera testnet.`
- Job status: `escrow_funded`
- `hedera_tx_id` in the response (format: `0.0.8600977@XXXXXXXXXX.XXXXXXXXX`)
- **Hashscan check:** `https://hashscan.io/testnet/transaction/{hedera_tx_id}` — shows 1.5 HBAR transfer from owner → escrow account
- **Hashscan check:** escrow account balance = `1.5 HBAR`

**Log to `live-e2e.md`:** `hedera_tx_id`, Hashscan link, escrow balance confirmation, screenshot

---

## Phase 5 — Supplier: Upload Proof (3 rooms)

**Actors:** Supplier (`0.0.9160906`)

**Steps:**
1. Sign out, log back in as **Supplier**
2. Go to **Jobs** → **Active** → select the job (status: `escrow_funded`)
3. In the upload section:
   - Upload `cleanbathroom.jpg` — label: **Bathroom**
   - Upload `cleanlivingroom.jpeg` — label: **Living Room**
   - Upload `clean-bedroom.webp` — label: **Bedroom**
4. Click **Mark complete** (or equivalent — "Mark ready for confirmation")

**Expected outcomes:**
- Each upload: notice `Proof uploaded for AI validation.`
- Job status after mark complete: `proof_uploaded` or `awaiting_confirmation`
- 3 photo records in the audit trail

**Log to `live-e2e.md`:** photo IDs, IPFS hashes (if available), status

---

## Phase 6 — Owner: Run AI Validation

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. Sign out, log back in as **Owner**
2. Go to **My Requests** → select the job (status: `proof_uploaded`)
3. The **Run AI validation** button should be visible
4. Click **Run AI validation**

**Expected outcomes:**
- Notice: `AI validation complete.`
- `AiValidation` panel shows status `passed`, confidence ~95%
- All 3 photos show green `passed` review status
- Job status: `awaiting_owner_confirmation`
- **Run AI validation** button disappears; **Confirm satisfaction** appears

**Log to `live-e2e.md`:** validation status, confidence score, photo statuses

---

## Phase 7 — Owner: Confirm Satisfaction

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. (Stay on the same job detail view)
2. Click **Confirm satisfaction**

**Expected outcomes:**
- Notice: `Owner satisfaction confirmed.`
- Job status: `completed`
- **Confirm satisfaction** button disappears; **Release payment** button appears

**Log to `live-e2e.md`:** status transition, timestamp

---

## Phase 8 — Owner: Release Payment → Hedera Transfer

**Actors:** Owner (`0.0.9160905`)

**Steps:**
1. Click **Release payment**

**Expected outcomes:**
- Notice: `Payment released to supplier on Hedera testnet.`
- Job status: `completed`, `escrow_status: released`
- `hedera_tx_id` in response (escrow → supplier transfer)
- **Hashscan check:** `https://hashscan.io/testnet/transaction/{hedera_tx_id}` — shows 1.5 HBAR transfer from escrow `0.0.XXXXXX` → supplier `0.0.9160906`
- Escrow account balance drained to near 0
- Supplier `0.0.9160906` balance increased by ~1.5 HBAR

**Log to `live-e2e.md`:** `hedera_tx_id`, Hashscan link, before/after balances, screenshot

---

## Phase 9 — Supplier: Verify Earnings

**Actors:** Supplier (`0.0.9160906`)

**Steps:**
1. Sign out, log back in as **Supplier**
2. Go to **Earnings** in the sidebar
3. Check `past_earnings` value

**Expected outcomes:**
- `past_earnings` includes the `150_000_000` tinybar (1.5 HBAR) from the released job
- Job appears in **Archived** tab with status `completed`

**Log to `live-e2e.md`:** earnings value, archived job status

---

## Hashscan Summary Table

Fill in during the test:

| Event | Hedera TX ID | Hashscan Link | Pass/Fail |
|-------|-------------|---------------|-----------|
| Escrow account created | `0.0.XXXXXX` | https://hashscan.io/testnet/account/... | |
| Escrow funded (owner → escrow) | `0.0.8600977@...` | https://hashscan.io/testnet/transaction/... | |
| Payment released (escrow → supplier) | `0.0.8600977@...` | https://hashscan.io/testnet/transaction/... | |

---

## Pass Criteria

- [ ] Real Hedera escrow account created on testnet
- [ ] 1.5 HBAR moved from `DEV_OWNER` → escrow account (verifiable on Hashscan)
- [ ] Proof photos uploaded (3 images, 3 rooms)
- [ ] AI validation passes
- [ ] 1.5 HBAR released from escrow → supplier `0.0.9160906` (verifiable on Hashscan)
- [ ] All status transitions correct: `quote_requested` → `quote_accepted` → `escrow_funded` → `proof_uploaded` → `awaiting_owner_confirmation` → `completed`
- [ ] No unhandled errors in backend or browser console

---

## Known Limitations (this session)

- AI validation uses a **mock** model (passes if any photos are uploaded) — real OpenRouter vision call is wired but not triggered in this flow
- `VITE_WALLET_ENABLED=false` — HashPack not involved; server uses `DEV_OWNER_PRIVATE_KEY` to fund
- Auth signature verification is disabled (`AUTH_REQUIRE_SIGNATURE=false`) — mock signatures work
- `room_or_area_label` is not sent in the upload `FormData` — the proof API accepts it but the UI wires `room_id` instead; photos will be labelled generically

---

## Rollback / Cleanup

- Each test creates a new job + Hedera escrow account. Testnet accounts are not deleted — they persist with near-zero HBAR after release.
- To rerun: just start a new flow (each test uses fresh request IDs).
- Testnet HBAR is free — top up at `https://portal.hedera.com/register` if `DEV_OWNER` balance runs low.
