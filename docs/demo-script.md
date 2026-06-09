# EscrowEye MVP Demo Script

## Setup

1. Start the backend and frontend.
2. Open `http://localhost:5173`.
3. Use Owner account `0.0.1111` or any mock Owner account.
4. Use Supplier account `0.0.2222` or any mock Supplier account.
5. Optional: call `POST /api/demo/seed` after login to create a seeded job.

## Demo Flow

1. Owner creates a profile and opens the desktop workspace.
2. Owner browses service categories and workers.
3. Owner requests a quote for a cleaning job.
4. x402 returns a payment requirement; replay with the demo payment header.
5. Supplier logs in and sees the request in Offers.
6. Supplier sends a quote.
7. Owner accepts the quote.
8. Owner funds escrow.
9. Supplier uploads proof images/videos.
10. EscrowEye AI validation runs and marks proof as passed.
11. Owner confirms satisfaction.
12. EscrowEye releases payment.
13. Show audit events and Hedera/HCS status.

## Judge Pitch

EscrowEye coordinates service work with payment commitment, proof upload, AI validation, and an audit trail designed for Hedera HCS. The MVP keeps local fallback behavior for demo reliability and isolates HCS/x402 integrations behind infrastructure services so testnet credentials can be added without changing product code.
