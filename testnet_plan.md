# EscrowEye — Testnet Integration Plan (v2)

## Intent

EscrowEye is a platform where homeowners pay cleaners via Hedera escrow — trustless,
transparent, automated.

The core loop:
1. **Create request** → owner pays a small creation fee via x402 (HBAR/USDC)
2. **Quote + Accept** → suppliers send quotes, owner picks one, escrow account is created
3. **Fund** → owner sends the job amount into escrow (wallet → escrow account)
4. **Work + Verify** → cleaner does the work, uploads photos, AI reviews them
5. **Release** → owner confirms satisfaction → escrow pays the cleaner

The owner's wallet is the source of truth for authentication and for **funding**.
The platform operator key does everything else: creates accounts, releases funds, manages disputes.

---

## Architecture

### Two API flows (critical distinction)

The codebase has **two separate escrow flows**:

| Flow | Endpoints | Service | Used by |
|---|---|---|---|
| **Marketplace (UI)** | `/api/service-requests/*` | `marketplace.py` | Browser frontend |
| **Agent (API)** | `/api/jobs/*` | `job_service.py` | LangGraph agent tools |

**Both flows use the same `EscrowService` (`escrow.py`) and the same `HEDERA_NETWORK` env var.**
They must both be wired to testnet independently.

### Escrow key structure: 1-of-1 (operator only)

```
Escrow Account Key = KeyList([operator_public_key], threshold=1)
```

- **Platform operator** signs every outgoing transfer (release, refund, dispute)
- **Owner** only sends money *in* (no signing power needed for deposits)
- **Supplier** has no signing power

### Three modes (controlled by `HEDERA_NETWORK` in `.env`)

| Mode | `HEDERA_NETWORK` | Escrow creation | Funding | Release |
|---|---|---|---|---|
| **Dev** | `""` or `dev` | Simulated (fake `0.0.99xxx` ID) | Simulated (instant) | Simulated (fake tx hash) |
| **Testnet** | `testnet` | Real SDK call, operator signs | Server uses `DEV_OWNER_PRIVATE_KEY` (Mode 2) or wallet sends real HBAR (Mode 3) | Real SDK call, operator signs |
| **Mainnet** | `mainnet` | Real SDK call, operator signs | Client wallet sends HBAR → server polls balance | Real SDK call, operator signs |

---

## Mode selection: how to switch between Mode 2 and Mode 3

Mode 2 and Mode 3 both run under `HEDERA_NETWORK=testnet`. The selection is:

- **Backend — implicit, driven by the request body.**
  The `POST /api/service-requests/{id}/fund-escrow` endpoint accepts an optional
  `{ transaction_id?: string }` body. The service checks:
  - `transaction_id` **present** → Mode 3 path: wallet already sent HBAR, server polls
    balance until it arrives, records `transaction_id` as the Hedera tx reference.
  - `transaction_id` **absent** → Mode 2 path: server signs a `TransferTransaction`
    from `DEV_OWNER_PRIVATE_KEY` → escrow account.
  No extra env var is needed on the backend. The same endpoint, same service function.

- **Frontend — one env var: `VITE_WALLET_ENABLED`.**
  Set in `frontend/.env.local` (gitignored):
  - `VITE_WALLET_ENABLED=false` (or unset) → **Mode 2**: the "Fund escrow" button calls
    `POST /api/service-requests/{id}/fund-escrow` with no body. Server handles everything.
    No wallet required. Good for smoke-testing testnet SDK calls without HashPack.
  - `VITE_WALLET_ENABLED=true` → **Mode 3**: the button label changes to
    "Fund with HashPack". On click: calls `transferHbar()` via HashConnect, gets back a
    `transactionId`, then calls `POST /api/service-requests/{id}/fund-escrow { transaction_id }`.
    Server polls balance instead of funding.

### Summary table

| What to change | Mode 2 (server funds) | Mode 3 (HashPack funds) |
|---|---|---|
| `.env` `HEDERA_NETWORK` | `testnet` | `testnet` |
| `frontend/.env.local` `VITE_WALLET_ENABLED` | `false` or unset | `true` |
| `frontend/.env.local` `VITE_WALLETCONNECT_PROJECT_ID` | not needed | `06b02ab5506a4012ace14e6cb2bc67f8` |
| HashConnect installed (`hashconnect@3.0.14`) | not needed | required |
| Request body on `fund-escrow` | empty `{}` | `{ transaction_id: "0.0.X@ts" }` |
| Who sends HBAR | Server (`DEV_OWNER_PRIVATE_KEY`) | User's HashPack wallet |

### `frontend/.env.local` for each mode

**Mode 1 (dev, fully simulated):**
```
VITE_API_BASE_URL=http://localhost:5103
# VITE_WALLET_ENABLED not set — defaults to false
```

**Mode 2 (testnet, server-side funding):**
```
VITE_API_BASE_URL=http://localhost:5103
VITE_WALLET_ENABLED=false
```

**Mode 3 (testnet + HashPack):**
```
VITE_API_BASE_URL=http://localhost:5103
VITE_WALLET_ENABLED=true
VITE_WALLETCONNECT_PROJECT_ID=06b02ab5506a4012ace14e6cb2bc67f8
```

---

## Current state (what is already done)

### Already implemented ✅

**`backend/app/core/config.py`**
- `HEDERA_NETWORK` property (reads env var, defaults to `"testnet"`)
- `hedera_is_real` property (true when `HEDERA_NETWORK` in `{"testnet", "mainnet"}`)

**`backend/app/services/escrow.py`**
- `create_escrow_account_with_public_keys(supplier_public_key)` — 1-of-1 operator KeyList, zero initial balance, operator signs
- `release_escrow(escrow_account_id, to_account_id, amount_tinybar)` — operator signs only
- `poll_balance(account_id, target_amount, timeout_secs)` — polls every 2s (**BUG: uses blocking `time.sleep` — see bugs section**)
- `get_balance(account_id)` — balance query
- `submit_signed_transaction(signed_tx_bytes)` — for future HashPack signed-tx flow

**`backend/app/services/job_service.py`** (agent flow only)
- `award_job`: when `hedera_is_real` → calls `EscrowService().create_escrow_account_with_public_keys(supplier_pub_key)`
- `fund_job(transaction_id?)`: when `hedera_is_real` → polls balance; without wallet returns `awaiting_funding` with escrow ID
- `confirm_job`: when `hedera_is_real` → calls `EscrowService().release_escrow()`

**`backend/app/api/routes/jobs.py`**
- `FundJobIn` model with optional `transaction_id`
- `fund_job` route accepts body

**`backend/agent/tools.py`**
- `fund_escrow(job_id, transaction_id?)` — first call bodyless returns `awaiting_funding`; second call with `transaction_id` confirms
- `check_funding(job_id)` — polls job status

**`backend/.env`** (project root, gitignored)
```
HEDERA_NETWORK=testnet
HEDERA_OPERATOR_ID=0.0.8600977
HEDERA_OPERATOR_PRIVATE_KEY=0xdb6ade6c843ae6614b4fe9202a22a3c85ecfe0c0ef158693606f5170025d0366
DEV_OWNER_ID=0.0.9160905
DEV_OWNER_PRIVATE_KEY=d992aef7c1fd79649d4b55a1be8fb543c71efdd6d7e4d19b06faf89912310d5e
DEV_OWNER_PUBLIC_KEY=302d300706052b8104000a03220003ab24aaa0cbe543902fec1a19ebf686381d1699a712bfc9e9a2ca48012691cc98
DEV_SUPPLIER_ID=0.0.9160906
DEV_SUPPLIER_PRIVATE_KEY=272592d1d12a7a8385032eb9bc3600c7db15bc05d06ab4a985fc17066cb2e850
DEV_SUPPLIER_PUBLIC_KEY=302d300706052b8104000a032200033bf7cec97de73a306b6f2ccaf9b7c5674850604e3fa29dfc952b17e0b04f5319
WALLETCONNECT_PROJECT_ID=06b02ab5506a4012ace14e6cb2bc67f8
OPENROUTER_API_KEY=sk-or-v1-...
PINATA_JWT=eyJ...
```

**`backend/app/core/config.py`**
- `load_dotenv()` called in `Settings.__new__` — `.env` at project root is auto-loaded on startup

### NOT yet done ❌

**`backend/app/services/marketplace.py`** (UI flow)
- Still fully simulated — fake escrow IDs (`0.0.{99000+id}`), fake tx hashes (`local:...`)
- `EscrowService` is never imported or called
- `accept_quote`, `fund_escrow`, `release_payment` ignore `HEDERA_NETWORK`

---

## Known bugs to fix before implementing

### Bug 1: `escrow.py` — `poll_balance` blocks the async event loop

```python
# CURRENT (WRONG — blocks every request handler while sleeping):
def poll_balance(self, account_id: str, target_amount: int, timeout_secs: int = 30) -> bool:
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        balance = self.get_balance(account_id)
        if balance >= target_amount:
            return True
        time.sleep(2)          # ← blocks event loop
    return False
```

```python
# FIX — make async, use asyncio.sleep:
import asyncio

async def poll_balance(self, account_id: str, target_amount: int, timeout_secs: int = 30) -> bool:
    import time
    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        balance = self.get_balance(account_id)
        if balance >= target_amount:
            return True
        await asyncio.sleep(2)
    return False
```

Also update all call sites in `job_service.py` to `await escrow_svc.poll_balance(...)`.

### Bug 2: `escrow.py` — `supplier_pub` parsed but never used

```python
# CURRENT (dead code — supplier_pub is parsed but not added to KeyList):
def create_escrow_account_with_public_keys(self, supplier_public_key: str) -> str:
    supplier_pub = self._parse_public_key(supplier_public_key)   # ← unused
    threshold_key = KeyList(keys=[self.operator_key.public_key()], threshold=1)
    ...
```

```python
# FIX — remove the unused parse (parameter kept for API compatibility + future use):
def create_escrow_account_with_public_keys(self, supplier_public_key: str) -> str:
    threshold_key = KeyList(keys=[self.operator_key.public_key()], threshold=1)
    ...
```

---

## Mode 2: Testnet + server-side funding (no wallet)

**Goal:** The full UI marketplace flow hits real Hedera testnet. The server uses
`DEV_OWNER_PRIVATE_KEY` from `.env` to fund escrow. No frontend changes needed.

**When `HEDERA_NETWORK=testnet`:**
- `accept_quote` → creates a real escrow account on Hedera testnet
- `fund_escrow` → server signs a `TransferTransaction` from `DEV_OWNER_ID` → escrow account
- `release_payment` → operator signs a `TransferTransaction` from escrow → supplier

### Changes required

---

#### `backend/app/services/escrow.py` — add `fund_from_dev_owner`

Add this method to `EscrowService` (after `release_escrow`):

```python
def fund_from_dev_owner(self, escrow_account_id: str, amount_tinybar: int) -> str:
    """Fund escrow from the DEV_OWNER account (Mode 2 — server-side, no wallet).
    Reads DEV_OWNER_PRIVATE_KEY and DEV_OWNER_ID from environment.
    Only used when HEDERA_NETWORK=testnet|mainnet and no client wallet is present."""
    from .hedera_client import get_dev_id, get_dev_key
    owner_key = get_dev_key("owner")
    owner_id = get_dev_id("owner")
    escrow_id = AccountId.from_string(escrow_account_id)
    tx = TransferTransaction()
    tx.add_hbar_transfer(owner_id, -amount_tinybar)
    tx.add_hbar_transfer(escrow_id, amount_tinybar)
    tx.freeze_with(self.client)
    tx.sign(owner_key)
    resp = tx.execute(self.client)
    return str(resp.transaction_id)
```

---

#### `backend/app/services/marketplace.py` — wire EscrowService

**Add these imports at the top:**
```python
from app.core.config import settings
from app.services.escrow import EscrowService
```

---

**Update `accept_quote`** — create real escrow account after accepting:

After the lines that set `job.supplier_user_id`, `job.accepted_bid_id`, `job.status = QUOTE_ACCEPTED`,
add:

```python
if settings.hedera_is_real:
    supplier_result = await session.execute(select(User).where(User.id == bid.supplier_user_id))
    supplier = supplier_result.scalar_one()
    escrow_svc = EscrowService()
    escrow_id = escrow_svc.create_escrow_account_with_public_keys(
        supplier.hedera_public_key or ""
    )
    job.escrow_account_id = escrow_id
    logger.info(
        "escrow.account_created request_id=%s escrow_id=%s",
        bid.job_id, escrow_id,
    )
```

Also update the return value to include `escrow_account_id`:
```python
return {
    "request_id": bid.job_id,
    "quote_id": quote_id,
    "status": JobStatus.QUOTE_ACCEPTED,
    "quote_amount": bid.amount_tinybar,
    "base_commitment_fee": base_fee_for(bid.amount_tinybar),
    "escrow_status": EscrowStatus.BASE_FEE_REQUIRED,
    "escrow_account_id": job.escrow_account_id,   # ← add this
}
```

---

**Update `fund_escrow`** — branch on `hedera_is_real`:

Replace the body of `fund_escrow` with:

```python
async def fund_escrow(session: AsyncSession, request_id: int, user: dict[str, Any]) -> dict[str, Any]:
    job_result = await session.execute(select(Job).where(Job.id == request_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.owner_user_id != user["id"]:
        raise HTTPException(status_code=403, detail="owner_role_required")
    if job.accepted_bid_id is None:
        raise HTTPException(status_code=409, detail="quote_not_accepted")

    bid_result = await session.execute(select(Bid).where(Bid.id == job.accepted_bid_id))
    bid = bid_result.scalar_one()
    now = datetime.now(UTC).isoformat()

    if settings.hedera_is_real:
        if not job.escrow_account_id:
            raise HTTPException(status_code=409, detail="escrow_not_created")
        if job.status == JobStatus.ESCROW_FUNDED:
            return {
                "request_id": request_id,
                "status": JobStatus.ESCROW_FUNDED,
                "escrow_status": EscrowStatus.ESCROW_FUNDED,
                "escrow_account_id": job.escrow_account_id,
            }
        escrow_svc = EscrowService()
        tx_id = escrow_svc.fund_from_dev_owner(job.escrow_account_id, bid.amount_tinybar)
        escrow = job.escrow_account_id
    else:
        escrow = f"0.0.{99000 + request_id}"
        tx_id = f"local:escrow:{request_id}"
        job.escrow_account_id = escrow

    job.status = JobStatus.ESCROW_FUNDED
    job.updated_at = now
    await record_transaction(session, request_id, "escrow_fund", bid.amount_tinybar, "HBAR", "settled", tx_id)
    await add_audit(session, request_id, "escrow_funded", {"amount": bid.amount_tinybar, "tx_id": tx_id})
    logger.info(
        "escrow.funded request_id=%s owner_wallet=%s amount=%s escrow=%s tx_id=%s",
        request_id, user["hedera_account_id"], bid.amount_tinybar, escrow, tx_id,
    )
    return {
        "request_id": request_id,
        "status": JobStatus.ESCROW_FUNDED,
        "escrow_status": EscrowStatus.ESCROW_FUNDED,
        "escrow_account_id": escrow,
        "hedera_tx_id": tx_id,
    }
```

---

**Update `release_payment`** — branch on `hedera_is_real`:

Replace `tx_id = f"local:release:{request_id}"` block with:

```python
if settings.hedera_is_real:
    if not job.escrow_account_id:
        raise HTTPException(status_code=409, detail="escrow_not_created")
    supplier_result = await session.execute(select(User).where(User.id == job.supplier_user_id))
    supplier = supplier_result.scalar_one()
    escrow_svc = EscrowService()
    tx_id = escrow_svc.release_escrow(job.escrow_account_id, supplier.hedera_account_id, amount)
else:
    tx_id = f"local:release:{request_id}"
```

Keep the rest of `release_payment` (record_transaction, add_audit, logger, return) unchanged.

---

### What Mode 2 does NOT change

- Frontend — zero changes
- `pay_base_fee` — stays as DB-only write (bookkeeping only, no HBAR transfer for Mode 2)
- `AUTH_REQUIRE_SIGNATURE` — stays `false`, mock signatures still work for login
- Agent flow (`job_service.py`) — already done, no changes needed

---

## Mode 3: Testnet + HashPack (HashConnect v3.0.14)

**Goal:** Real wallet UX. HashPack signs the auth challenge + sends real HBAR to escrow.
Built on top of Mode 2. No backend escrow logic changes — Mode 2 covers the dev path;
Mode 3 just adds the wallet path on top.

### Package versions (confirmed via npm)

- `hashconnect@3.0.14` — latest stable, uses WalletConnect v2 protocol
- Peer deps bundled: `@walletconnect/sign-client@2.11.2`, `@walletconnect/modal@2.6.2`
- **Requires** `WALLETCONNECT_PROJECT_ID` (already in `.env` as `WALLETCONNECT_PROJECT_ID=06b02ab5506a4012ace14e6cb2bc67f8`)

### Changes required

---

#### `frontend/` — install package

```bash
cd frontend && npm install hashconnect@3.0.14
```

---

#### `frontend/.env.local` (new file, gitignored) — expose project ID to Vite

```
VITE_WALLETCONNECT_PROJECT_ID=06b02ab5506a4012ace14e6cb2bc67f8
VITE_API_BASE_URL=http://localhost:5103
```

---

#### `frontend/src/services/hashconnect.ts` (new file)

Wrap the HashConnect v3 `DAppConnector`. Expose a singleton with:

```typescript
import { HashConnect } from "hashconnect";
import { LedgerId } from "@hashgraph/sdk";

const APP_METADATA = {
  name: "EscrowEye",
  description: "Hedera escrow for home services",
  icons: ["https://escroweye.app/logo.png"],
  url: window.location.origin,
};

let hc: HashConnect | null = null;

export function getHashConnect(): HashConnect {
  if (!hc) {
    hc = new HashConnect(
      LedgerId.TESTNET,
      import.meta.env.VITE_WALLETCONNECT_PROJECT_ID,
      APP_METADATA,
      true,   // debug
    );
  }
  return hc;
}

export async function connectHashPack(): Promise<{ accountId: string; publicKey: string }> {
  const hashconnect = getHashConnect();
  await hashconnect.init();
  const state = await hashconnect.openPairingModal();
  const accountId = state.accountIds[0];
  const publicKey = ""; // derive from accountId via mirror node if needed
  return { accountId, publicKey };
}

export async function signChallengeWithHashPack(message: string): Promise<string> {
  // HashConnect v3 signs arbitrary messages via the connected signer
  const hashconnect = getHashConnect();
  const signer = hashconnect.getSigner(hashconnect.connectedAccountIds[0]);
  const signed = await signer.sign([Buffer.from(message)]);
  return Buffer.from(signed[0].signature).toString("hex");
}

export async function transferHbarWithHashPack(
  toAccountId: string,
  amountTinybar: number,
): Promise<{ transactionId: string }> {
  const { TransferTransaction, AccountId, Hbar, HbarUnit } = await import("@hashgraph/sdk");
  const hashconnect = getHashConnect();
  const signer = hashconnect.getSigner(hashconnect.connectedAccountIds[0]);
  const fromAccountId = hashconnect.connectedAccountIds[0];

  const tx = await new TransferTransaction()
    .addHbarTransfer(AccountId.fromString(fromAccountId), Hbar.fromTinybars(-amountTinybar))
    .addHbarTransfer(AccountId.fromString(toAccountId), Hbar.fromTinybars(amountTinybar))
    .freezeWithSigner(signer);

  const result = await tx.executeWithSigner(signer);
  return { transactionId: result.transactionId.toString() };
}
```

---

#### `frontend/src/wallet.ts` — update to use HashConnect

Add `transferHbar` export. Update `signWalletChallenge` to use HashConnect when available:

```typescript
import { connectHashPack, signChallengeWithHashPack, transferHbarWithHashPack } from "./services/hashconnect";

// Replace findWalletSigner() usage with HashConnect-aware logic
export async function signWalletChallenge(message: string, devSignature: string): Promise<SignedWalletChallenge> {
  // Try HashConnect first (v3 WalletConnect flow)
  try {
    const { accountId, publicKey } = await connectHashPack();
    const signature = await signChallengeWithHashPack(message);
    return { signature, accountId, publicKey, source: "wallet" };
  } catch {
    // Fall back to window injection (legacy) then dev mock
  }

  // Legacy window injection fallback
  const signer = findWalletSigner();
  if (signer) { /* existing logic */ }

  return { signature: devSignature, source: "dev" };
}

export async function transferHbar(
  toAccountId: string,
  amountTinybar: number,
): Promise<{ transactionId: string }> {
  return transferHbarWithHashPack(toAccountId, amountTinybar);
}
```

---

#### `frontend/src/features/workspace/components.tsx` — Fund with HashPack button

In the owner's request detail panel (wherever `escrow_account_id` and `quote_amount` are available),
add a conditional "Fund with HashPack" button:

```tsx
// Show when: job has escrow_account_id set AND status is quote_accepted (not yet funded)
{job.escrow_account_id && job.status === "quote_accepted" && (
  <FundEscrowButton
    escrowAccountId={job.escrow_account_id}
    amountTinybar={job.quote_amount!}
    requestId={job.id}
    onFunded={() => { /* refresh workspace */ }}
  />
)}
```

`FundEscrowButton` component:
```tsx
function FundEscrowButton({ escrowAccountId, amountTinybar, requestId, onFunded }) {
  const [state, setState] = useState<"idle" | "signing" | "polling" | "done">("idle");

  async function handleFund() {
    setState("signing");
    const { transactionId } = await transferHbar(escrowAccountId, amountTinybar);
    setState("polling");
    await api.fundEscrow(requestId, transactionId);
    setState("done");
    onFunded();
  }

  if (state === "signing") return <p>Waiting for HashPack signature…</p>;
  if (state === "polling") return <p>Confirming on Hedera testnet…</p>;
  if (state === "done") return <p>Escrow funded ✓</p>;
  return (
    <button className="primary-button" onClick={handleFund}>
      Fund with HashPack ({tinybarToHbar(amountTinybar)} HBAR)
    </button>
  );
}
```

---

#### `frontend/src/services/escroweyeClient.ts` — add `fundEscrow` method

```typescript
fundEscrow: (jobId: number, transactionId?: string) =>
  request(`/api/service-requests/${jobId}/fund-escrow`, {
    method: "POST",
    body: JSON.stringify({ transaction_id: transactionId ?? null }),
  }),
```

---

#### `backend/app/api/routes/escrow.py` — accept `transaction_id` body on fund-escrow

```python
class FundEscrowIn(BaseModel):
    transaction_id: str | None = None

@router.post("/service-requests/{request_id}/fund-escrow")
async def fund_service_escrow(
    request_id: int,
    body: FundEscrowIn = FundEscrowIn(),
    user: dict[str, Any] = Depends(current_user),
):
    async with db() as session:
        return await marketplace_service.fund_escrow(session, request_id, user, body.transaction_id)
```

---

#### `backend/app/services/marketplace.py` — handle wallet `transaction_id` in `fund_escrow`

Update `fund_escrow` signature to accept optional `transaction_id`:

```python
async def fund_escrow(
    session: AsyncSession,
    request_id: int,
    user: dict[str, Any],
    transaction_id: str | None = None,   # ← new param
) -> dict[str, Any]:
```

When `hedera_is_real` and `transaction_id` is provided (Mode 3 — wallet funded it):
```python
if settings.hedera_is_real:
    if not job.escrow_account_id:
        raise HTTPException(status_code=409, detail="escrow_not_created")
    if job.status == JobStatus.ESCROW_FUNDED:
        return { ...already funded... }

    escrow_svc = EscrowService()

    if transaction_id:
        # Mode 3: wallet already sent the HBAR — poll to confirm balance arrived
        confirmed = await escrow_svc.poll_balance(job.escrow_account_id, bid.amount_tinybar, 30)
        if not confirmed:
            return {
                "request_id": request_id,
                "status": "funding_timeout",
                "escrow_account_id": job.escrow_account_id,
                "amount_tinybar": bid.amount_tinybar,
            }
        tx_id = transaction_id
    else:
        # Mode 2: server funds using DEV_OWNER_PRIVATE_KEY
        tx_id = escrow_svc.fund_from_dev_owner(job.escrow_account_id, bid.amount_tinybar)

    escrow = job.escrow_account_id
else:
    # Dev mode: simulate
    escrow = f"0.0.{99000 + request_id}"
    tx_id = f"local:escrow:{request_id}"
    job.escrow_account_id = escrow
```

---

### What Mode 3 does NOT change

- `release_payment` — operator key releases, no wallet needed (same as Mode 2)
- `accept_quote` escrow creation — operator key creates account (same as Mode 2)
- Backend auth validation — `AUTH_REQUIRE_SIGNATURE` can optionally be set to `true` to require
  HashPack to sign the auth challenge; if `false` (current default) mock signatures still work

---

## Testing strategy

### Unit/integration tests (always run, `HEDERA_NETWORK` not set or empty)

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ --ignore=tests/test_hedera_testnet.py -v
```

Tests to update as part of Mode 2:
- `tests/test_marketplace_api.py` — mock `EscrowService` (patch `marketplace.EscrowService`);
  assert `create_escrow_account_with_public_keys` called on `accept_quote`,
  `fund_from_dev_owner` called on `fund_escrow`, `release_escrow` called on `release_payment`
- `tests/test_hedera.py` — update `poll_balance` call sites to `await` (it's now async)
- `tests/test_integration.py` — no changes needed

### Real testnet tests (run with `HEDERA_NETWORK=testnet`)

```bash
HEDERA_NETWORK=testnet python -m pytest tests/test_hedera_testnet.py -v
```

`test_hedera_testnet.py` already covers the basic SDK cycle (create → fund → release).
Add a marketplace-specific test:

```python
def test_marketplace_escrow_cycle():
    """Simulates the full UI flow: accept_quote creates escrow,
    fund_from_dev_owner sends HBAR, release_escrow pays supplier."""
    from app.services.escrow import EscrowService
    from app.services.hedera_client import get_dev_id, get_dev_key

    svc = EscrowService()
    supplier_pub = get_dev_key("supplier").public_key()

    # Step 1: accept_quote creates escrow
    escrow_id = svc.create_escrow_account_with_public_keys(str(supplier_pub))
    assert escrow_id.startswith("0.0.")

    # Step 2: fund_escrow uses dev owner key
    amount = 1_00000000  # 1 HBAR
    tx_id = svc.fund_from_dev_owner(escrow_id, amount)
    assert "@" in tx_id  # Hedera tx ID format: 0.0.X@timestamp

    # Step 3: balance confirmed
    balance = svc.get_balance(escrow_id)
    assert balance == amount

    # Step 4: release_payment sends to supplier
    supplier_id = str(get_dev_id("supplier"))
    release_tx = svc.release_escrow(escrow_id, supplier_id, amount)
    assert "@" in release_tx

    # Balance drained
    assert svc.get_balance(escrow_id) < 1_000000
```

### Frontend build check

```bash
cd frontend && npm run build
```

---

## Implementation order

### Phase 1: Fix bugs (do first, independent of modes)

1. `escrow.py` — fix `poll_balance` blocking sleep → `async` + `asyncio.sleep`
2. `escrow.py` — remove unused `supplier_pub` variable in `create_escrow_account_with_public_keys`
3. Update `job_service.py` call sites: `escrow_svc.poll_balance(...)` → `await escrow_svc.poll_balance(...)`
4. Run tests to confirm nothing broken

### Phase 2: Mode 2 (testnet, no wallet)

5. `escrow.py` — add `fund_from_dev_owner` method
6. `marketplace.py` — add imports (`settings`, `EscrowService`)
7. `marketplace.py` — update `accept_quote` (create real escrow when `hedera_is_real`)
8. `marketplace.py` — update `fund_escrow` (branch on `hedera_is_real`, server-side fund via `DEV_OWNER_PRIVATE_KEY`)
9. `marketplace.py` — update `release_payment` (branch on `hedera_is_real`, real `release_escrow`)
10. `backend/app/api/routes/escrow.py` — add `FundEscrowIn` body model (`transaction_id?: str`), update route signature
11. `tests/test_marketplace_api.py` — mock `marketplace.EscrowService`; assert the three methods are called in testnet mode, not called in dev mode
12. Create `frontend/.env.local` with `VITE_API_BASE_URL=http://localhost:5103` and `VITE_WALLET_ENABLED=false`
13. Run full test suite, confirm green
14. Manual smoke test: start both servers, create request → accept quote → fund escrow → check Hashscan for real tx

### Phase 3: Mode 3 (testnet + HashPack)

15. `cd frontend && npm install hashconnect@3.0.14`
16. Update `frontend/.env.local` — add `VITE_WALLET_ENABLED=true` + `VITE_WALLETCONNECT_PROJECT_ID`
17. Create `frontend/src/services/hashconnect.ts`
18. Update `frontend/src/wallet.ts` — add `transferHbar`, update `signWalletChallenge` to try HashConnect first
19. Update `frontend/src/services/escroweyeClient.ts` — add `fundEscrow(jobId, transactionId?)` method
20. Update `frontend/src/features/workspace/components.tsx` — add `FundEscrowButton` (reads `VITE_WALLET_ENABLED` to decide label + behaviour)
21. Update `backend/app/services/marketplace.py` `fund_escrow` — add `transaction_id` param, add Mode 3 poll-balance branch
22. Run frontend build, connect HashPack in browser, full end-to-end smoke test

---

## Running the servers

```bash
# Backend — testnet mode auto-loaded from .env at project root
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 5103

# Frontend — reads VITE_* vars from frontend/.env.local (created in Phase 2)
cd frontend && npx vite --port 5173
```

**`frontend/.env.local`** controls which mode the UI uses (see Mode Selection section above).
Create this file once; it is gitignored. Never pass `VITE_*` on the command line — use `.env.local`.
