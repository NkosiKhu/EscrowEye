# EscrowEye

Two-party property inspection escrow on **Hedera**.

A requester deposits HBAR into escrow and opens an inspection job. An inspector submits photos. They go back and forth (more photos, clarifications) until both are satisfied. When both parties confirm via their agents, escrow releases to the inspector.

---

## Stack

| Layer       | Technology                                   |
| ----------- | -------------------------------------------- |
| Backend     | FastAPI + Uvicorn (Python 3.12)              |
| Frontend    | React + TypeScript + Vite                    |
| Ledger      | Hedera (HCS for logging, HBAR for escrow)    |
| Photos      | IPFS via Pinata (CIDs logged to HCS)         |
| Wallet      | HashPack                                     |
| Gate        | x402 (blocky402.com) on job creation         |
| Testing     | Playwright                                   |
| Docs        | Context7                                     |

---

## Architecture

```
┌────────────┐     ┌──────────────┐     ┌────────────┐
│  Requester │◄───►│  EscrowEye   │◄───►│  Inspector │
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

1. **Creation** — Requester pays x402 fee → job created on-chain via HCS message
2. **Deposit** — Requester deposits HBAR into escrow
3. **Inspection** — Inspector submits photos (IPFS) → logged to HCS
4. **Exchange** — Back-and-forth photo requests, clarifications via HCS
5. **Confirmation** — Both parties (via agents) sign off
6. **Release** — Escrow releases HBAR to inspector

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

## Open Questions

| Question                | Status |
| ----------------------- | ------ |
| Escrow mechanism        | TBD — multisig account vs smart contract |
| Auth strategy           | TBD — HashPack signatures, JWTs, or other |
| Deployment target       | TBD — VPS, K8s, Railway, etc. |

---

## Contributing

This is a shared dev project. Push to `main` after review.
