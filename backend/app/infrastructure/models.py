from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    user_type: Mapped[str] = mapped_column(String, nullable=False)
    hedera_account_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hedera_public_key: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    service_area: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_token_preference: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    homes: Mapped[list[Home]] = relationship("Home", back_populates="owner", cascade="all, delete-orphan")
    supplier_profile: Mapped[SupplierProfile | None] = relationship("SupplierProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Challenge(Base):
    __tablename__ = "challenges"

    nonce: Mapped[str] = mapped_column(String, primary_key=True)
    hedera_account_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class Home(Base):
    __tablename__ = "homes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    owner: Mapped[User] = relationship("User", back_populates="homes")
    rooms: Mapped[list[Room]] = relationship("Room", back_populates="home", cascade="all, delete-orphan")
    jobs: Mapped[list[Job]] = relationship("Job", back_populates="home", cascade="all, delete-orphan")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    home_id: Mapped[int] = mapped_column(Integer, ForeignKey("homes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sq_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    home: Mapped[Home] = relationship("Home", back_populates="rooms")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    home_id: Mapped[int] = mapped_column(Integer, ForeignKey("homes.id", ondelete="CASCADE"), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    supplier_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_bid_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_price_tinybar: Mapped[int] = mapped_column(Integer, nullable=False)
    access_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_times: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    escrow_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    hcs_topic_id: Mapped[str] = mapped_column(String, nullable=False)
    creation_fee_paid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    home: Mapped[Home] = relationship("Home", back_populates="jobs")
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_user_id])
    supplier: Mapped[User | None] = relationship("User", foreign_keys=[supplier_user_id])
    bids: Mapped[list[Bid]] = relationship("Bid", back_populates="job", cascade="all, delete-orphan")
    messages: Mapped[list[Message]] = relationship("Message", back_populates="job", cascade="all, delete-orphan")
    photos: Mapped[list[Photo]] = relationship("Photo", back_populates="job", cascade="all, delete-orphan")
    audit_events: Mapped[list[AuditEvent]] = relationship("AuditEvent", back_populates="job", cascade="all, delete-orphan")
    ai_validations: Mapped[list[AIValidation]] = relationship("AIValidation", back_populates="job", cascade="all, delete-orphan")
    escrow_transactions: Mapped[list[EscrowTransaction]] = relationship("EscrowTransaction", back_populates="job", cascade="all, delete-orphan")
    proof_uploads: Mapped[list[ProofUpload]] = relationship("ProofUpload", back_populates="job", cascade="all, delete-orphan")


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    supplier_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    amount_tinybar: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="bids")
    supplier: Mapped[User] = relationship("User")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    sender_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    sender_type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="messages")


class MessagePhoto(Base):
    __tablename__ = "message_photos"

    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    cid: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(String, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_keys: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="photos")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    consensus_timestamp: Mapped[str] = mapped_column(String, nullable=False)
    hcs_status: Mapped[str] = mapped_column(String, nullable=False, default="local_only")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    job: Mapped[Job] = relationship("Job", back_populates="audit_events")


class AIValidation(Base):
    __tablename__ = "ai_validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    issues_found: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_corrections: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="ai_validations")


class EscrowTransaction(Base):
    __tablename__ = "escrow_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    hedera_tx_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="escrow_transactions")


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    services_offered: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    portfolio_items: Mapped[str | None] = mapped_column(Text, nullable=True)
    average_rate: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="supplier_profile")


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProofUpload(Base):
    __tablename__ = "proof_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    photo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_url: Mapped[str] = mapped_column(String, nullable=False)
    cid: Mapped[str] = mapped_column(String, nullable=False)
    room_or_area_label: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    job: Mapped[Job] = relationship("Job", back_populates="proof_uploads")
