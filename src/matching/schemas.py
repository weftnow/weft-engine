"""Versioned matching service contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    """Console-compatible camelCase wire format with Pythonic internal names."""

    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True
    )


class LifecycleContext(APIModel):
    complete: bool
    prior_decisions: list[tuple[UUID, UUID]]
    protected_pairs: list[tuple[UUID, UUID]]
    completed_pairs: list[tuple[UUID, UUID]]


class CreateRun(APIModel):
    mode: Literal["event", "more"]
    target_guest_id: UUID | None = None
    lifecycle: LifecycleContext

    @model_validator(mode="after")
    def valid_target(self) -> CreateRun:
        if not self.lifecycle.complete:
            raise ValueError("lifecycle context must be explicitly complete")
        if (self.mode == "more") != (self.target_guest_id is not None):
            raise ValueError("target_guest_id is required only for more calculations")
        return self


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_id: UUID
    field: Literal[
        "summary", "goals", "offers", "desiredConnections", "background", "linkedinDetails"
    ]
    quote: str = Field(min_length=1, max_length=500)


class PairEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_a_id: UUID
    guest_b_id: UUID
    benefit_a: str = Field(min_length=10, max_length=600)
    benefit_b: str = Field(min_length=10, max_length=600)
    score_a: int = Field(ge=0, le=100)
    score_b: int = Field(ge=0, le=100)
    evidence: list[Evidence]
    missing_information_a: list[str]
    missing_information_b: list[str]
    uncertainty: str = Field(max_length=600)
    restriction_found: bool


class PairEvaluationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairs: list[PairEvaluation] = Field(min_length=1, max_length=4)


class EvidenceVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    valid_evidence_indexes: list[int]
    shareable_reasons: dict[str, str | None]


class RunAccepted(APIModel):
    run_id: UUID
    status: Literal["waiting", "running", "failed", "finished", "invalid_result"]


class ResultItem(APIModel):
    recommendation_id: UUID
    guest_low_id: UUID
    guest_high_id: UUID
    profile_versions: dict[str, int]
    directional_scores: dict[str, int]
    pair_score: int
    benefits: dict[str, str | None]
    evidence: list[dict[str, str]]
    missing_information: dict[str, list[str]]
    uncertainty: str
    shareable_reasons: dict[str, str | None]


class ResultsResponse(APIModel):
    run_id: UUID
    status: str
    snapshot_fingerprint: str
    source_run_id: UUID
    guest_reasons: dict[str, str]
    recommendations: list[ResultItem]
