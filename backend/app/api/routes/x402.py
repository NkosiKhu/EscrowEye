from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.infrastructure.x402_service import X402Service

router = APIRouter(prefix="/api/x402", tags=["x402"])
x402_service = X402Service()


@router.get("/job-creation/payment-requirements")
def x402_job_creation_requirements():
    return {"payment_requirements": x402_service.payment_requirements()}


@router.post("/verify")
def x402_verify(body: dict[str, Any]):
    return x402_service.verify(body)


@router.post("/settle")
def x402_settle(body: dict[str, Any]):
    return x402_service.settle(body)
