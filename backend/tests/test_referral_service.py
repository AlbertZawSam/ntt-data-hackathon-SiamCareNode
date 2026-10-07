from datetime import timedelta

import pytest
from pydantic import ValidationError

from siamcare.composition import build_hospital_service
from siamcare.errors import (
    ActorPermissionError,
    InvalidInputError,
    NotFoundError,
    TransitionError,
)
from siamcare.models.referral import (
    ActorContext,
    CreateReferral,
    ReferralStatus,
    RequestStatus,
)
from siamcare.repositories.sqlite_referral_repository import SqliteReferralRepository
from siamcare.services.referral_service import ReferralService

CLINICIAN = ActorContext(actor_id="demo-clinician", role="clinician")
APPROVER = ActorContext(actor_id="demo-physician", role="approver")
STAFF = ActorContext(actor_id="demo-staff", role="hospital_staff", hospital_id="H01")
DATA = CreateReferral(
    patient_reference="SYN-001", specialty=" Neurology ", urgency="routine"
)


@pytest.fixture
def workflow(tmp_path):
    repository = SqliteReferralRepository(tmp_path / "workflow.sqlite3")
    return ReferralService(repository, build_hospital_service())


@pytest.fixture
def opened(workflow):
    return workflow.create_referral(DATA, CLINICIAN)


@pytest.fixture
def pending(workflow, opened):
    return workflow.send_request(opened.referral_id, "H01", CLINICIAN)


@pytest.fixture
def review(workflow, pending):
    workflow.respond_to_request(
        pending.request_id, STAFF, accept=True, reason="Demo ready"
    )
    return workflow.submit_for_review(pending.referral_id, CLINICIAN)


def snapshot(workflow, referral_id):
    return (
        workflow.get_referral(referral_id),
        workflow.list_requests(referral_id=referral_id),
        workflow.history(referral_id),
    )


def test_complete_approval(workflow, review):
    approved = workflow.decide_referral(review.referral_id, APPROVER, approve=True)
    assert approved.status == ReferralStatus.APPROVED
    assert approved.version == 4
    assert approved.specialty == "neurology"
    assert approved.referring_clinician_id == CLINICIAN.actor_id
    request = workflow.get_request(approved.selected_request_id)
    assert request.status == RequestStatus.ACCEPTED
    assert request.response_reason == "Demo ready"
    assert workflow.list_requests(hospital_id="H01") == (request,)
    assert workflow.list_referrals() == (approved,)
    events = workflow.history(approved.referral_id)
    assert [e.action.value for e in events] == [
        "created",
        "request_sent",
        "request_accepted",
        "review_submitted",
        "approved",
    ]
    assert len({e.event_id for e in events}) == 5
    assert [e.version for e in events] == list(range(5))
    assert events[-1].actor_id == APPROVER.actor_id
    assert events[-1].actor_role == "approver"
    assert events[-1].details["from_status"] == "awaiting_review"
    assert events[-1].details["to_status"] == "approved"
    for timestamp in [
        approved.created_at,
        approved.updated_at,
        request.responded_at,
        *[event.timestamp for event in events],
    ]:
        assert timestamp.utcoffset() == timedelta(0)
    assert build_hospital_service().get_hospital("H01").free_beds == 4


def test_decline_then_another_hospital(workflow, pending):
    declined = workflow.respond_to_request(
        pending.request_id, STAFF, accept=False, reason="  Demo ward closed  "
    )
    assert declined.status == RequestStatus.DECLINED
    assert declined.response_reason == "Demo ward closed"
    referral = workflow.get_referral(pending.referral_id)
    assert referral.status == ReferralStatus.OPEN
    assert referral.selected_request_id is None
    second = workflow.send_request(referral.referral_id, "H06", CLINICIAN)
    assert second.request_id != declined.request_id
    assert len(workflow.list_requests(referral_id=referral.referral_id)) == 2
    other_staff = ActorContext(
        actor_id="other-staff", role="hospital_staff", hospital_id="H06"
    )
    workflow.respond_to_request(second.request_id, other_staff, accept=True)
    workflow.submit_for_review(referral.referral_id, CLINICIAN)
    workflow.decide_referral(referral.referral_id, APPROVER, approve=True)
    assert workflow.get_request(declined.request_id) == declined
    assert (
        workflow.history(referral.referral_id)[2].details["reason"]
        == "Demo ward closed"
    )


def test_physician_rejection(workflow, review):
    before = workflow.get_request(review.selected_request_id)
    result = workflow.decide_referral(
        review.referral_id, APPROVER, approve=False, reason="  Demo review declined  "
    )
    assert result.status == ReferralStatus.REJECTED
    cancelled = workflow.get_request(review.selected_request_id)
    assert cancelled.status == RequestStatus.CANCELLED
    assert cancelled.response_reason == before.response_reason
    assert cancelled.responded_at == before.responded_at
    assert (
        workflow.history(review.referral_id)[-1].details["reason"]
        == "Demo review declined"
    )


@pytest.mark.parametrize("hospital", ["H02", "H03"])
def test_unsuitable_or_zero_capacity(workflow, opened, hospital):
    before = snapshot(workflow, opened.referral_id)
    with pytest.raises(InvalidInputError, match="at least one"):
        workflow.send_request(opened.referral_id, hospital, CLINICIAN)
    assert snapshot(workflow, opened.referral_id) == before
    assert [h.hospital_id for h in workflow.find_hospitals(opened.referral_id)] == [
        "H01",
        "H06",
    ]


@pytest.mark.parametrize(
    "operation",
    [
        lambda s: s.get_referral("missing"),
        lambda s: s.get_request("missing"),
        lambda s: s.history("missing"),
        lambda s: s.find_hospitals("missing"),
        lambda s: s.send_request("missing", "H01", CLINICIAN),
        lambda s: s.respond_to_request("missing", STAFF, accept=True),
        lambda s: s.submit_for_review("missing", CLINICIAN),
        lambda s: s.decide_referral("missing", APPROVER, approve=True),
        lambda s: s.list_requests(referral_id="missing"),
        lambda s: s.list_requests(hospital_id="missing"),
    ],
)
def test_unknown_ids(workflow, operation):
    with pytest.raises(NotFoundError):
        operation(workflow)


def test_unknown_hospital(workflow, opened):
    with pytest.raises(NotFoundError):
        workflow.send_request(opened.referral_id, "missing", CLINICIAN)
    assert len(workflow.history(opened.referral_id)) == 1


@pytest.mark.parametrize(
    "operation",
    [
        lambda s, r: s.send_request(r.referral_id, "H06", CLINICIAN),
        lambda s, r: s.submit_for_review(r.referral_id, CLINICIAN),
        lambda s, r: s.decide_referral(r.referral_id, APPROVER, approve=True),
        lambda s, r: s.decide_referral(
            r.referral_id, APPROVER, approve=False, reason="No"
        ),
    ],
)
def test_invalid_pending_transitions(workflow, pending, operation):
    before = snapshot(workflow, pending.referral_id)
    with pytest.raises(TransitionError):
        operation(workflow, pending)
    assert snapshot(workflow, pending.referral_id) == before


@pytest.mark.parametrize("first_accept", [True, False])
@pytest.mark.parametrize("repeat_accept", [True, False])
def test_repeated_or_conflicting_hospital_response(
    workflow, pending, first_accept, repeat_accept
):
    workflow.respond_to_request(
        pending.request_id, STAFF, accept=first_accept, reason="Demo"
    )
    before = snapshot(workflow, pending.referral_id)
    with pytest.raises(TransitionError, match="pending"):
        workflow.respond_to_request(
            pending.request_id, STAFF, accept=repeat_accept, reason="Demo"
        )
    assert snapshot(workflow, pending.referral_id) == before


@pytest.mark.parametrize("approve", [True, False])
def test_terminal_referrals(workflow, review, approve):
    workflow.decide_referral(
        review.referral_id, APPROVER, approve=approve, reason="Demo"
    )
    before = snapshot(workflow, review.referral_id)
    actions = [
        lambda: workflow.send_request(review.referral_id, "H06", CLINICIAN),
        lambda: workflow.submit_for_review(review.referral_id, CLINICIAN),
        lambda: workflow.decide_referral(review.referral_id, APPROVER, approve=True),
        lambda: workflow.decide_referral(
            review.referral_id, APPROVER, approve=False, reason="No"
        ),
    ]
    for action in actions:
        with pytest.raises(TransitionError):
            action()
        assert snapshot(workflow, review.referral_id) == before


def test_repeated_review_submission(workflow, review):
    before = snapshot(workflow, review.referral_id)
    with pytest.raises(TransitionError):
        workflow.submit_for_review(review.referral_id, CLINICIAN)
    assert snapshot(workflow, review.referral_id) == before


@pytest.mark.parametrize("reason", [None, "", " \t\n "])
def test_decline_reason_required(workflow, pending, reason):
    before = snapshot(workflow, pending.referral_id)
    with pytest.raises(InvalidInputError, match="nonblank reason"):
        workflow.respond_to_request(
            pending.request_id, STAFF, accept=False, reason=reason
        )
    assert snapshot(workflow, pending.referral_id) == before


@pytest.mark.parametrize("reason", [None, "", " \t\n "])
def test_rejection_reason_required(workflow, review, reason):
    before = snapshot(workflow, review.referral_id)
    with pytest.raises(InvalidInputError, match="nonblank reason"):
        workflow.decide_referral(
            review.referral_id, APPROVER, approve=False, reason=reason
        )
    assert snapshot(workflow, review.referral_id) == before


def test_wrong_hospital(workflow, pending):
    actor = ActorContext(
        actor_id="wrong-staff", role="hospital_staff", hospital_id="H06"
    )
    before = snapshot(workflow, pending.referral_id)
    with pytest.raises(ActorPermissionError, match="actor's hospital"):
        workflow.respond_to_request(pending.request_id, actor, accept=True)
    assert snapshot(workflow, pending.referral_id) == before


@pytest.mark.parametrize("approve", [True, False])
def test_self_review(workflow, review, approve):
    actor = ActorContext(actor_id=CLINICIAN.actor_id, role="approver")
    before = snapshot(workflow, review.referral_id)
    with pytest.raises(ActorPermissionError, match="own referral"):
        workflow.decide_referral(
            review.referral_id, actor, approve=approve, reason="Demo"
        )
    assert snapshot(workflow, review.referral_id) == before


@pytest.mark.parametrize(
    "operation",
    [
        lambda s, r: s.create_referral(DATA, APPROVER),
        lambda s, r: s.send_request(r.referral_id, "H06", APPROVER),
        lambda s, r: s.respond_to_request(
            r.selected_request_id, CLINICIAN, accept=True
        ),
        lambda s, r: s.submit_for_review(r.referral_id, STAFF),
        lambda s, r: s.decide_referral(r.referral_id, CLINICIAN, approve=True),
        lambda s, r: s.decide_referral(
            r.referral_id, STAFF, approve=False, reason="Demo"
        ),
    ],
)
def test_wrong_roles(workflow, review, operation):
    before = snapshot(workflow, review.referral_id)
    with pytest.raises(ActorPermissionError):
        operation(workflow, review)
    assert snapshot(workflow, review.referral_id) == before
    assert len(workflow.list_referrals()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"patient_reference": " "},
        {"specialty": " "},
        {"urgency": "emergency"},
    ],
)
def test_create_validation(changes):
    with pytest.raises(ValidationError):
        CreateReferral.model_validate({**DATA.model_dump(), **changes})


def test_urgency_must_be_explicit():
    with pytest.raises(ValidationError, match="urgency"):
        CreateReferral(patient_reference="SYN-001", specialty="neurology")


def test_staff_requires_scope():
    with pytest.raises(ValidationError, match="hospital_id"):
        ActorContext(actor_id="demo", role="hospital_staff")
