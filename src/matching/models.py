"""Engine-owned PostgreSQL records. All tables are confined to weft_engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata for the engine schema only."""

    metadata_schema = "weft_engine"


class Run(Base):
    __tablename__ = "matching_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_id",
            "idempotency_key",
            name="matching_runs_idempotency_unique",
        ),
        CheckConstraint("mode IN ('event','more')", name="matching_runs_mode_valid"),
        CheckConstraint(
            "status IN ('waiting','running','failed','finished','invalid_result')",
            name="matching_runs_status_valid",
        ),
        CheckConstraint("trigger IN ('api','change')", name="matching_runs_trigger_valid"),
        Index("matching_runs_queue_idx", "status", "created_at"),
        Index("matching_runs_event_idx", "organization_id", "event_id", "created_at"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    target_guest_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="api")
    change_batch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class Attempt(Base):
    __tablename__ = "matching_attempts"
    __table_args__ = (
        Index("matching_attempts_run_idx", "run_id", "created_at"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BudgetReservation(Base):
    """Durable cost reservation; unknown billing remains charged until reconciled."""

    __tablename__ = "matching_budget_reservations"
    __table_args__ = (
        CheckConstraint("state IN ('reserved','settled','unknown')", name="matching_budget_state"),
        {"schema": Base.metadata_schema},
    )

    attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("weft_engine.matching_attempts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("weft_engine.matching_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    reserved_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    actual_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="reserved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VerificationCache(Base):
    """Successful evidence verification tied to exact content and privacy context."""

    __tablename__ = "matching_verifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_id",
            "input_fingerprint",
            "privacy_fingerprint",
            "model",
            "verifier_version",
            name="matching_verifications_cache_unique",
        ),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    privacy_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(100), nullable=False)
    live_attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("weft_engine.matching_attempts.id"), nullable=False
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScreeningCache(Base):
    """Experimental screening cache, structurally separate from full evaluations."""

    __tablename__ = "matching_screenings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_id",
            "input_fingerprint",
            "model",
            "screening_version",
            name="matching_screenings_cache_unique",
        ),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    screening_version: Mapped[str] = mapped_column(String(100), nullable=False)
    live_attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("weft_engine.matching_attempts.id"), nullable=False
    )
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Embedding(Base):
    __tablename__ = "matching_embeddings"
    __table_args__ = (
        UniqueConstraint("organization_id", "guest_id", "channel", "content_fingerprint", "model"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    guest_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    values: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    live_attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "guest_low_id", "guest_high_id", name="recommendations_pair_unique"
        ),
        CheckConstraint("guest_low_id < guest_high_id", name="recommendations_pair_order"),
        CheckConstraint("pair_score BETWEEN 70 AND 100", name="recommendations_score_valid"),
        CheckConstraint(
            "revocation_reason IS NULL OR revocation_reason IN "
            "('guest_excluded','pair_blocked','identity_resolution_required','guest_missing')",
            name="recommendations_revocation_reason_valid",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revocation_reason IS NULL)",
            name="recommendations_revocation_consistent",
        ),
        Index("recommendations_event_idx", "organization_id", "event_id", "created_at"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    guest_low_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    guest_high_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_versions: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    directional_scores: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    pair_score: Mapped[int] = mapped_column(Integer, nullable=False)
    benefits: Mapped[dict[str, str | None]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    missing_information: Mapped[dict[str, list[str]]] = mapped_column(JSONB, nullable=False)
    uncertainty: Mapped[str] = mapped_column(Text, nullable=False)
    shareable_reasons: Mapped[dict[str, str | None]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(48))
    revoked_by_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class SlotGrant(Base):
    __tablename__ = "matching_slot_grants"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_id",
            "request_key",
            name="matching_slot_grants_request_unique",
        ),
        CheckConstraint("slots=3", name="matching_slot_grants_slots_valid"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    guest_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(String(200), nullable=False)
    slots: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EvaluationCache(Base):
    __tablename__ = "matching_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "pair_fingerprint",
            "model",
            "prompt_version",
            "policy_version",
            name="matching_evaluations_cache_unique",
        ),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pair_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    live_attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChangeBatch(Base):
    """One coalesced set of Console changes answered by one run per attempt."""

    __tablename__ = "matching_change_batches"
    __table_args__ = (
        CheckConstraint(
            "state IN ('scheduled','completed','abandoned')", name="matching_change_batches_state"
        ),
        Index("matching_change_batches_event_idx", "organization_id", "event_id", "state"),
        {"schema": Base.metadata_schema},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    last_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    abandon_reason: Mapped[str | None] = mapped_column(String(80))


class ChangeReceipt(Base):
    """Idempotent engine-side record that a Console change row was read."""

    __tablename__ = "matching_change_receipts"
    __table_args__ = (
        Index("matching_change_receipts_event_idx", "event_id", "batch_id", "change_created_at"),
        {"schema": Base.metadata_schema},
    )

    change_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    guest_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)
    change_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    batch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class FeedEntry(Base):
    """Pull-feed item; seq order within an event matches commit order (written under the lock)."""

    __tablename__ = "matching_feed_entries"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "kind", name="matching_feed_entries_once"),
        CheckConstraint("kind IN ('issued','revoked')", name="matching_feed_entries_kind"),
        Index("matching_feed_entries_event_idx", "organization_id", "event_id", "seq"),
        {"schema": Base.metadata_schema},
    )

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    recommendation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
