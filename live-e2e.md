# EscrowEye Live E2E Test Log

**Date:** 2026-06-09  
**Backend:** http://localhost:5103  
**Frontend:** http://localhost:5173  
**Config:** `.env` loaded — `HEDERA_NETWORK=testnet`, operator `0.0.8600977`

---

## Architecture note (pre-test finding)

The frontend UI calls `/api/service-requests` (marketplace flow → `marketplace.py`).  
That flow uses **simulated** escrow throughout — fake account IDs, instant funded, no real SDK calls.

The **real** Hedera testnet calls (from testnet_plan.md changes) live in `/api/jobs` (agent flow → `job_service.py` + `escrow.py`).

**Implication:** The full UI end-to-end flow will complete successfully in testnet config, but escrow funding and release will be **simulated** (fake `0.0.99xxx` account IDs). Real SDK calls only fire if the agent tools use the `/api/jobs` endpoints or the testnet cycle test runs.

---

## Full E2E Flow

### Step 1 — Owner login

- **Action:** Navigate to http://localhost:5173, select Owner role, fill account `0.0.9160905`, click Connect.
- **API calls:**
  - `POST /api/auth/challenge` — get nonce
  - `POST /api/auth/login` — mock signature accepted (AUTH_REQUIRE_SIGNATURE=false)

