from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUOTE_REQUESTED = "quote_requested"
    QUOTE_RECEIVED = "quote_received"
    QUOTE_ACCEPTED = "quote_accepted"
    BASE_FEE_PAID = "base_fee_paid"
    ESCROW_FUNDED = "escrow_funded"
    PROCESSING = "processing"
    PROOF_UPLOADED = "proof_uploaded"
    AI_REVIEWING = "ai_reviewing"
    NEEDS_REVISION = "needs_revision"
    AWAITING_OWNER_CONFIRMATION = "awaiting_owner_confirmation"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class EscrowStatus(str, Enum):
    NOT_STARTED = "not_started"
    BASE_FEE_REQUIRED = "base_fee_required"
    BASE_FEE_PAID = "base_fee_paid"
    ESCROW_PENDING = "escrow_pending"
    ESCROW_FUNDED = "escrow_funded"
    RELEASE_READY = "release_ready"
    RELEASED = "released"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


class AIValidationStatus(str, Enum):
    WAITING_FOR_PROOF = "waiting_for_proof"
    REVIEWING = "reviewing"
    PASSED = "passed"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    DISPUTE_OPENED = "dispute_opened"
    RESOLVED = "resolved"
