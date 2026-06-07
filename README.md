# EscrowEye

Two-party property cleaning escrow on **Hedera**.

An owner pays an x402 job-submission fee, creates a cleaning job, accepts a supplier bid, and funds HBAR escrow. The supplier submits encrypted IPFS photos, the EscrowEye agent reviews them in the job chat, and escrow releases to the supplier after confirmation.

---

## Stack

| Layer       | Technology                                      |
| ----------- | ----------------------------------------------- |
| Backend     | FastAPI + Uvicorn (Python 3.12)                 |
| Frontend    | React + TypeScript + Vite + shadcn-style UI     |
| Agent       | Hedera Agent Kit + LangGraph + OpenRouter GPT-4o |
| Ledger      | Hedera HCS audit events + HBAR escrow           |
| Photos      | IPFS via Pinata, CIDs stored in SQLite          |
| Wallet      | HashPack via WalletConnect                      |
| Gate        | x402 with Blocky402 on `POST /api/jobs`         |
| Testing     | Playwright                                      |

---

## Architecture

```
┌────────────┐     ┌──────────────┐     ┌────────────┐
│   Owner    │◄───►│  EscrowEye   │◄───►│  Supplier  │
│  (HashPack)│     │   (API + UI) │     │  (HashPack)│
└─────┬──────┘     └──────┬───────┘     └─────┬──────┘
      │                   │                    │
      │          ┌────────┴────────┐           │
      │          │    Hedera       │           │
      │          │  ┌──────────┐   │           │
      ├──────────┼──┤ HCS Topics│   │           │
      │          │  └──────────┘   │           │
      │          │  ┌──────────┐   │           │
      ├──────────┼──┤ HBAR     │   │           │
      │          │  │ Escrow   │   │           │
      │          │  └──────────┘   │           │
      │          └────────┬────────┘           │
      │                   │                    │
      │          ┌────────┴────────┐           │
      └──────────┤    IPFS/Pinata  │◄──────────┘
                 └─────────────────┘
```

### Job Flow

1. **Creation** — Owner posts a job through `POST /api/jobs`; unpaid requests return x402 `402 Payment Required`, then the paid replay creates the job and writes `job_created` to HCS.
2. **Bidding** — Suppliers browse open jobs and place bids with `amount_tinybar`.
3. **Deposit** — Owner accepts a bid and funds a Hedera escrow account.
4. **Inspection** — Supplier submits encrypted photos to IPFS; photo CIDs and encrypted key metadata stay in SQLite.
5. **Agent Review** — The chat-panel agent reviews photos, assigns rooms, and requests retakes or posts an all-clear message.
6. **Confirmation** — Supplier marks ready, owner confirms with HashPack, and escrow releases HBAR to the supplier.
7. **Audit** — HCS records exactly three event types in the MVP: `job_created`, `job_completed`, and `job_disputed`.

### Demo Shape

The public demo is a hosted web app, not a standalone chatbot. The primary screen is a normal shadcn-style job workspace with an optional full-height/full-screen agent chat panel that can create/setup jobs instead of using the manual forms.

For Week 3 submission, the video should show:

1. Owner connects HashPack.
2. Owner asks the chat-panel agent to create a job or uses the regular form.
3. `POST /api/jobs` triggers the x402/Blocky402 payment flow.
4. Paid replay creates the job and the app shows the agent confirmation.
5. Supplier photo upload triggers agent review in the same conversation.

---

## Local Development

```bash
docker compose up --build
```

- Backend: http://localhost:8000 — `GET /` returns `{"app":"EscrowEye","status":"ok"}`
- Frontend: http://localhost:5173 — Vite dev server with HMR

### Backend (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend (without Docker)

```bash
cd frontend
npm install
npm run dev
```

---

## Project Structure

```
EscrowEye/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py          # FastAPI entry point
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## Decisions

| Question                | Status |
| ----------------------- | ------ |
| Escrow mechanism        | Hedera native 2-of-3 threshold account |
| Auth strategy           | JWT session plus HashPack wallet signatures |
| x402 gate               | Native `402 Payment Required` on `POST /api/jobs` |
| HCS scope               | `job_created`, `job_completed`, `job_disputed` only |
| Deployment target       | Publicly hosted app, video acceptable for submission |

---

## Contributing

This is a shared dev project. Push to `main` after review.
