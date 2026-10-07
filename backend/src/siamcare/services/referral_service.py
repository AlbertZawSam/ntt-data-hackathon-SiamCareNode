"""Local referral rules; no transport, database connection, or terminal dependencies."""

from datetime import UTC, datetime
from uuid import uuid4

from siamcare.errors import (
    ActorPermissionError,
    InvalidInputError,
    NotFoundError,
    TransitionError,
)
from siamcare.models.hospital import Hospital
from siamcare.models.referral import (
    ActorContext,
    ActorRole,
    CreateReferral,
    EventAction,
    HospitalRequest,
    Referral,
    ReferralEvent,
    ReferralStatus,
    RequestStatus,
)
from siamcare.repositories.referral_repository import ReferralRepository
from siamcare.services.hospital_service import HospitalService

# There are no outgoing transitions from either physician decision in this phase.
TRANSITIONS = {
    EventAction.REQUEST_SENT: (ReferralStatus.OPEN, ReferralStatus.AWAITING_HOSPITAL),
    EventAction.REQUEST_ACCEPTED: (
        ReferralStatus.AWAITING_HOSPITAL,
        ReferralStatus.HOSPITAL_ACCEPTED,
    ),
    EventAction.REQUEST_DECLINED: (
        ReferralStatus.AWAITING_HOSPITAL,
        ReferralStatus.OPEN,
    ),
    EventAction.REVIEW_SUBMITTED: (
        ReferralStatus.HOSPITAL_ACCEPTED,
        ReferralStatus.AWAITING_REVIEW,
    ),
    EventAction.APPROVED: (ReferralStatus.AWAITING_REVIEW, ReferralStatus.APPROVED),
    EventAction.REJECTED: (ReferralStatus.AWAITING_REVIEW, ReferralStatus.REJECTED),
}


class ReferralService:
    def __init__(
        self, repository: ReferralRepository, hospitals: HospitalService
    ) -> None:
        self._repository = repository
        self._hospitals = hospitals

    def get_referral(self, referral_id: str) -> Referral:
        referral = self._repository.get_referral(referral_id)
        if referral is None:
            raise NotFoundError(f"Referral {referral_id!r} not found")
        return referral

    def list_referrals(self) -> tuple[Referral, ...]:
        return self._repository.list_referrals()

    def get_request(self, request_id: str) -> HospitalRequest:
        request = self._repository.get_request(request_id)
        if request is None:
            raise NotFoundError(f"Request {request_id!r} not found")
        return request

    def list_requests(
        self, *, referral_id: str | None = None, hospital_id: str | None = None
    ) -> tuple[HospitalRequest, ...]:
        if referral_id is None and hospital_id is None:
            raise InvalidInputError("Supply a referral_id or hospital_id")
        if referral_id is not None:
            self.get_referral(referral_id)
        if hospital_id is not None:
            self._hospitals.get_hospital(hospital_id)
        return self._repository.list_requests(
            referral_id=referral_id, hospital_id=hospital_id
        )

    def history(self, referral_id: str) -> tuple[ReferralEvent, ...]:
        self.get_referral(referral_id)
        return self._repository.history(referral_id)

    def find_hospitals(self, referral_id: str) -> tuple[Hospital, ...]:
        referral = self.get_referral(referral_id)
        return self._hospitals.search_hospitals(referral.specialty, min_free_beds=1)

    def create_referral(self, data: CreateReferral, actor: ActorContext) -> Referral:
        self._require_role(actor, ActorRole.CLINICIAN)
        now = datetime.now(UTC)
        referral = Referral(
            **data.model_dump(),
            referral_id=str(uuid4()),
            referring_clinician_id=actor.actor_id,
            status=ReferralStatus.OPEN,
            created_at=now,
            updated_at=now,
            version=0,
        )
        event = self._event(referral, EventAction.CREATED, actor, None)
        self._repository.create(referral, event)
        return referral

    def send_request(
        self, referral_id: str, hospital_id: str, actor: ActorContext
    ) -> HospitalRequest:
        self._require_role(actor, ActorRole.CLINICIAN)
        referral = self.get_referral(referral_id)
        self._require_transition(referral, EventAction.REQUEST_SENT)
        hospital = self._hospitals.get_hospital(hospital_id)
        # Recheck capabilities and capacity; discovery does not reserve anything.
        eligible = self._hospitals.search_hospitals(referral.specialty, min_free_beds=1)
        if hospital.hospital_id not in {item.hospital_id for item in eligible}:
            raise InvalidInputError(
                f"Hospital {hospital_id!r} must support {referral.specialty!r} "
                "and have at least one recorded free bed"
            )
        request = HospitalRequest(
            request_id=str(uuid4()),
            referral_id=referral_id,
            hospital_id=hospital_id,
            status=RequestStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        self._transition(referral, EventAction.REQUEST_SENT, actor, request)
        return request

    def respond_to_request(
        self,
        request_id: str,
        actor: ActorContext,
        *,
        accept: bool,
        reason: str | None = None,
    ) -> HospitalRequest:
        self._require_role(actor, ActorRole.HOSPITAL_STAFF)
        request = self.get_request(request_id)
        if actor.hospital_id != request.hospital_id:
            raise ActorPermissionError(
                "Hospital response must match the actor's hospital"
            )
        reason = self._reason(reason, required=not accept)
        referral = self.get_referral(request.referral_id)
        if request.status != RequestStatus.PENDING:
            raise TransitionError(
                "Only a pending request can receive a hospital response"
            )
        if referral.selected_request_id != request_id:
            raise TransitionError("Request is not selected for this referral")
        action = (
            EventAction.REQUEST_ACCEPTED if accept else EventAction.REQUEST_DECLINED
        )
        self._require_transition(referral, action)
        updated = HospitalRequest.model_validate(
            {
                **request.model_dump(),
                "status": RequestStatus.ACCEPTED if accept else RequestStatus.DECLINED,
                "responded_at": datetime.now(UTC),
                "response_reason": reason,
            }
        )
        self._transition(referral, action, actor, updated, reason)
        return updated

    def submit_for_review(self, referral_id: str, actor: ActorContext) -> Referral:
        self._require_role(actor, ActorRole.CLINICIAN)
        referral = self.get_referral(referral_id)
        self._require_transition(referral, EventAction.REVIEW_SUBMITTED)
        self._accepted_request(referral)
        return self._transition(referral, EventAction.REVIEW_SUBMITTED, actor)

    def decide_referral(
        self,
        referral_id: str,
        actor: ActorContext,
        *,
        approve: bool,
        reason: str | None = None,
    ) -> Referral:
        self._require_role(actor, ActorRole.APPROVER)
        referral = self.get_referral(referral_id)
        # Role flags are demo inputs today. Verified identity belongs at the boundary,
        # but this separation-of-duties rule must remain enforced by the service.
        if actor.actor_id == referral.referring_clinician_id:
            raise ActorPermissionError(
                "Referring clinician cannot review their own referral"
            )
        action = EventAction.APPROVED if approve else EventAction.REJECTED
        self._require_transition(referral, action)
        reason = self._reason(reason, required=not approve)
        request = self._accepted_request(referral)
        cancelled = None
        if not approve:
            # Keep the hospital response; record the cancellation reason in the event.
            cancelled = HospitalRequest.model_validate(
                {
                    **request.model_dump(),
                    "status": RequestStatus.CANCELLED,
                }
            )
        return self._transition(referral, action, actor, cancelled, reason)

    def _accepted_request(self, referral: Referral) -> HospitalRequest:
        if referral.selected_request_id is None:
            raise TransitionError("Referral has no selected request")
        request = self.get_request(referral.selected_request_id)
        if request.status != RequestStatus.ACCEPTED:
            raise TransitionError("Only an accepted request can be reviewed")
        return request

    @staticmethod
    def _require_role(actor: ActorContext, role: ActorRole) -> None:
        if actor.role != role:
            raise ActorPermissionError(
                f"This action requires the demo {role.value} role"
            )

    @staticmethod
    def _reason(reason: str | None, *, required: bool) -> str | None:
        reason = reason.strip() if reason is not None else None
        if required and not reason:
            raise InvalidInputError("Declining or rejecting requires a nonblank reason")
        return reason or None

    @staticmethod
    def _require_transition(referral: Referral, action: EventAction) -> None:
        expected, _ = TRANSITIONS[action]
        if referral.status != expected:
            raise TransitionError(
                f"Cannot {action.value} a referral in {referral.status.value}; "
                f"expected {expected.value}"
            )

    def _transition(
        self,
        referral: Referral,
        action: EventAction,
        actor: ActorContext,
        request: HospitalRequest | None = None,
        reason: str | None = None,
    ) -> Referral:
        self._require_transition(referral, action)
        _, target = TRANSITIONS[action]
        selected = request.request_id if request else referral.selected_request_id
        if target == ReferralStatus.OPEN:
            selected = None
        updated = Referral.model_validate(
            {
                **referral.model_dump(),
                "status": target,
                "selected_request_id": selected,
                "updated_at": datetime.now(UTC),
                "version": referral.version + 1,
            }
        )
        event = self._event(updated, action, actor, referral.status, request, reason)
        # The adapter checks version and writes all three records in one transaction.
        self._repository.save_transition(updated, event, request)
        return updated

    @staticmethod
    def _event(
        referral: Referral,
        action: EventAction,
        actor: ActorContext,
        previous: ReferralStatus | None,
        request: HospitalRequest | None = None,
        reason: str | None = None,
    ) -> ReferralEvent:
        return ReferralEvent(
            event_id=str(uuid4()),
            referral_id=referral.referral_id,
            action=action,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            timestamp=referral.updated_at,
            version=referral.version,
            details={
                "from_status": previous.value if previous else None,
                "to_status": referral.status.value,
                "request_id": request.request_id
                if request
                else referral.selected_request_id,
                "request_status": request.status.value if request else None,
                "hospital_id": request.hospital_id if request else None,
                "actor_hospital_id": actor.hospital_id,
                "reason": reason,
            },
        )
