from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChallengeIn(BaseModel):
    hedera_account_id: str


class LoginIn(BaseModel):
    hedera_account_id: str
    hedera_public_key: str = ""
    signature: str = ""
    nonce: str
    user_type: str = Field(pattern="^(owner|supplier)$")


class ProfilePatch(BaseModel):
    email: Optional[str] = None


class HomeIn(BaseModel):
    name: str
    address: str


class RoomIn(BaseModel):
    name: str
    sq_meters: Optional[float] = None


class JobIn(BaseModel):
    home_id: int
    title: str
    description: str
    suggested_price_tinybar: int
    access_notes: Optional[str] = None
    available_times: Optional[str] = None


class BidIn(BaseModel):
    amount_tinybar: int
    message: Optional[str] = None


class AwardIn(BaseModel):
    bid_id: int


class ReadyIn(BaseModel):
    message: Optional[str] = None


class DisputeIn(BaseModel):
    reason: str


class MessageIn(BaseModel):
    body: str = ""
    photo_ids: list[int] = Field(default_factory=list)


class FundIn(BaseModel):
    signed_transaction: str = ""


class SignatureIn(BaseModel):
    signature: str = ""
    message: str = ""
    signed_transaction: str = ""


class PhotoPatch(BaseModel):
    room_id: Optional[int] = None
    review_status: Optional[str] = Field(default=None, pattern="^(pending|passed|failed|needs_retake)$")
    review_notes: Optional[str] = None
