from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.infrastructure.x402_service import X402ConfigurationError, X402Service


async def require_x402_payment(
    request: Request,
    x_payment: str | None = Header(default=None),
    x_402_payment: str | None = Header(default=None),
) -> dict[str, Any]:
    _ = x_payment, x_402_payment
    x402 = X402Service()
    try:
        payment = x402.authorize_headers(dict(request.headers))
    except X402ConfigurationError as error:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_verification_required",
                "detail": str(error),
                "payment_requirements": x402.payment_requirements(),
            },
        )
    if not payment.get("valid"):
        raise HTTPException(
            status_code=402,
            detail={
                "error": "payment_required",
                "payment_requirements": x402.payment_requirements(),
            },
        )
    return payment
