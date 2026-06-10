# EscrowEye — Live E2E Test Log

**Date:** 2026-06-10
**Mode:** Non-headless (visible browser)

---

## Phase 0 — Pre-flight

| Check | Result |
|-------|--------|
| Backend `GET /api/health` | ✅ 200 |
| Frontend `http://localhost:5173` | ✅ 200 |

---

## Phase 1 — Owner: Create Service Request

| Item | Value |
|------|-------|
| Request ID | #3 |
| Status | `quote_requested` |
| Notice | "Request #3 created with x402 payment." |
| Supplier | Chijioke Nwosu |
| Budget | 2 HBAR |
| Schedule | Sat, 1 Mar 2025 · 3:00PM |

**x402 Flow:** Initial submit returned 402 Payment Required (10000000 tinybar). Clicked "Replay paid request" to complete.

---

## Phase 2 — Supplier: Send Quote

| Item | Value |
|------|-------|
| Notice | "Quote sent." |
| Quote Amount | ₦220,000.00 |
| Status | Quote sent successfully |

**⚠️ BUG LOGGED:** Modal backdrop intercepts pointer events after quote success. Could not click Sign out or close modal via X button. Required manual DOM removal of `.modal-backdrop` to proceed. User confirmed same issue.

---

## Phase 3 — Owner: Accept Quote

| Item | Value |
|------|-------|
| Notice | "Quote accepted. Hedera escrow account created." |
| Status | `quote_accepted` |
| Escrow Account | `0.0.9178338` |
| Quote Amount | 2.2 HBAR |

---

## Phase 4 — Owner: Fund Escrow

| Item | Value |
|------|-------|
| Notice | "Escrow funded on Hedera testnet." |
| Status | `escrow_funded` |
| Escrow Account | `0.0.9178338` |
| Amount | 2.2 HBAR |

---

## Phase 5 — Supplier: Upload Proof (3 rooms)

| Image | File | Result |
|-------|------|--------|
| Bathroom | `cleanbathroom.jpg` | ✅ Proof #7 uploaded |
| Living Room | `cleanlivingroom.jpeg` | ✅ Uploaded |
| Bedroom | `clean-bedroom.webp` | ✅ Uploaded |

| Item | Value |
|------|-------|
| Notice | "Proof uploaded for AI validation." (x3) |
| Status | `awaiting_owner_confirmation` |
| Audit Trail | 17 events |

---

## Phase 6 — Owner: Run AI Validation

| Item | Value |
|------|-------|
| Notice | "AI validation complete." |
| Status | `awaiting_owner_confirmation` |
| Confidence | 72% |
| Audit Trail | 18 events |

---

## Phase 7 — Owner: Confirm Satisfaction

| Item | Value |
|------|-------|
| Status | ❌ **BLOCKED** |
| Error | "Failed to fetch" |
| Console Error | CORS policy: No 'Access-Control-Allow-Origin' header |
| API Response | 401 Unauthorized: `missing_bearer_token` |

**⚠️ BLOCKER:** The `/api/service-requests/2/confirm-satisfaction` endpoint returns CORS errors when called from the frontend. Direct API call returns 401 requiring bearer token. The auth flow requires a valid challenge/nonce which the frontend doesn't appear to be handling correctly.

---

## Phase 8 — Owner: Release Payment

| Item | Value |
|------|-------|
| Status | ⏸️ Not reached (blocked by Phase 7) |

---

## Phase 9 — Supplier: Verify Earnings

| Item | Value |
|------|-------|
| Status | ⏸️ Not reached (blocked by Phase 7) |

---

## Summary

### Completed Phases
- ✅ Phase 0: Pre-flight
- ✅ Phase 1: Owner creates service request (#3)
- ✅ Phase 2: Supplier sends quote (₦220,000.00)
- ✅ Phase 3: Owner accepts quote (escrow `0.0.9178338` created)
- ✅ Phase 4: Owner funds escrow (2.2 HBAR)
- ✅ Phase 5: Supplier uploads 3 proof images
- ✅ Phase 6: Owner runs AI validation (72% confidence)

### Blocked
- ❌ Phase 7: Confirm satisfaction — CORS + auth blocker
- ⏸️ Phase 8: Release payment
- ⏸️ Phase 9: Verify earnings

### Bugs Found
1. **Modal backdrop intercepts clicks** — After quote success, the modal backdrop remains and blocks all clicks. Requires manual DOM removal.
2. **CORS error on confirm-satisfaction** — Backend not returning proper CORS headers for this endpoint.
3. **Auth token missing** — Frontend not sending bearer token for protected endpoints.

### Hashscan Summary

| Event | Hedera Account/TX | Status |
|-------|-------------------|--------|
| Escrow account created | `0.0.9178338` | ✅ Created |
| Escrow funded | Pending verification | ⏸️ |
| Payment released | Not reached | ⏸️ |

### Status Transitions Observed
`quote_requested` → `quote_accepted` → `escrow_funded` → `awaiting_owner_confirmation` → ❌ (blocked)