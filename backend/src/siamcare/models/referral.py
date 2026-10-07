"""Validated workflow records. Status transitions belong to the service."""

from datetime import UTC
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from siamcare.models.hospital import NonBlank, normalize_specialty

UTCDateTime = Annotated[
    AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))
]


class Urgency(StrEnum):
    ROUTINE = "routine"
    TIME_CRITICAL = "time-critical"


class ActorRole(StrEnum):
    CLINICIAN = "clinician"
    HOSPITAL_STAFF = "hospital_staff"
    APPROVER = "approver"


class ActorContext(BaseModel):
    """Demo claims only; a future authenticated boundary must supply verified claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    actor_id: NonBlank
    role: ActorRole
    hospital_id: NonBlank | None = None

    @model_validator(mode="after")
    def require_hospital_scope(self) -> Self:
        if self.role == ActorRole.HOSPITAL_STAFF and self.hospital_id is None:
            raise ValueError("hospital_staff requires a hospital_id")
        return self


class ReferralStatus(StrEnum):
    OPEN = "open"
    AWAITING_HOSPITAL = "awaiting_hospital"
    HOSPITAL_ACCEPTED = "hospital_accepted"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class RequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class EventAction(StrEnum):
    CREATED = "created"
    REQUEST_SENT = "request_sent"
    REQUEST_ACCEPTED = "request_accepted"
    REQUEST_DECLINED = "request_declined"
    REVIEW_SUBMITTED = "review_submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class CreateReferral(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    patient_reference: NonBlank
    specialty: NonBlank
    urgency: Urgency

    @field_validator("specialty")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_specialty(value)


class Referral(CreateReferral):
    referral_id: NonBlank
    referring_clinician_id: NonBlank
    status: ReferralStatus
    selected_request_id: NonBlank | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    version: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if (self.status == ReferralStatus.OPEN) != (self.selected_request_id is None):
            raise ValueError("only open referrals have no selected request")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class HospitalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: NonBlank
    referral_id: NonBlank
    hospital_id: NonBlank
    status: RequestStatus
    response_reason: NonBlank | None = None
    created_at: UTCDateTime
    responded_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if (self.status == RequestStatus.PENDING) != (self.responded_at is None):
            raise ValueError("only pending requests have no response timestamp")
        if self.status == RequestStatus.PENDING and self.response_reason is not None:
            raise ValueError("pending requests cannot have a response reason")
        if self.status == RequestStatus.DECLINED and self.response_reason is None:
            raise ValueError("declining requires a nonblank reason")
        if self.responded_at is not None and self.responded_at < self.created_at:
            raise ValueError("responded_at cannot precede created_at")
        return self


class ReferralEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: NonBlank
    referral_id: NonBlank
    action: EventAction
    actor_id: NonBlank
    actor_role: ActorRole
    timestamp: UTCDateTime
    version: int = Field(ge=0, strict=True)
    details: dict[str, str | None]
