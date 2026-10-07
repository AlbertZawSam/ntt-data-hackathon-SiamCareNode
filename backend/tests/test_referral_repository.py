import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest

from siamcare.composition import build_hospital_service
from siamcare.errors import ConflictError, PersistenceError
from siamcare.models.referral import (
    ActorContext,
    CreateReferral,
    HospitalRequest,
    Referral,
    ReferralEvent,
)
from siamcare.repositories.sqlite_referral_repository import SqliteReferralRepository
from siamcare.services.referral_service import ReferralService

ACTOR = ActorContext(actor_id="demo-clinician", role="clinician")
DATA = CreateReferral(
    patient_reference="SYN-001", specialty="neurology", urgency="time-critical"
)


@pytest.fixture
def persisted(tmp_path):
    path = tmp_path / "nested" / "referrals.sqlite3"
    repository = SqliteReferralRepository(path)
    service = ReferralService(repository, build_hospital_service())
    referral = service.create_referral(DATA, ACTOR)
    return path, repository, service, referral


def test_reinitialization_and_independent_instances(persisted):
    path, repository, service, referral = persisted
    request = service.send_request(referral.referral_id, "H01", ACTOR)
    second = SqliteReferralRepository(path)
    third = SqliteReferralRepository(path)
    assert second.get_referral(referral.referral_id) == service.get_referral(
        referral.referral_id
    )
    assert third.get_request(request.request_id) == request
    assert third.history(referral.referral_id) == repository.history(
        referral.referral_id
    )
    assert third.list_requests(hospital_id="H06") == ()
    assert third.list_requests(referral_id=referral.referral_id) == (request,)


def test_event_failure_rolls_back_state_and_request(persisted):
    path, repository, service, referral = persisted
    # Fail at the last write, after the referral and new request have been written.
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON referral_events
            BEGIN SELECT RAISE(ABORT, 'injected event failure'); END""")
    with pytest.raises(PersistenceError, match="injected event failure"):
        service.send_request(referral.referral_id, "H01", ACTOR)
    assert repository.get_referral(referral.referral_id) == referral
    assert repository.list_requests(referral_id=referral.referral_id) == ()
    assert len(repository.history(referral.referral_id)) == 1
    with pytest.raises(PersistenceError):
        service.create_referral(DATA, ACTOR)
    assert repository.list_referrals() == (referral,)


def test_response_failure_preserves_pending_request(persisted):
    path, repository, service, referral = persisted
    request = service.send_request(referral.referral_id, "H01", ACTOR)
    before = repository.get_referral(referral.referral_id)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON referral_events
            BEGIN SELECT RAISE(ABORT, 'injected event failure'); END""")
    staff = ActorContext(actor_id="staff", role="hospital_staff", hospital_id="H01")
    with pytest.raises(PersistenceError):
        service.respond_to_request(request.request_id, staff, accept=True)
    assert repository.get_referral(referral.referral_id) == before
    assert repository.get_request(request.request_id) == request
    assert len(repository.history(referral.referral_id)) == 2


def test_simultaneous_sends_only_one_commits(persisted):
    path, repository, _, referral = persisted
    barrier = Barrier(2)

    class SynchronizedRepository(SqliteReferralRepository):
        def save_transition(self, referral, event, request=None):
            barrier.wait(timeout=10)
            super().save_transition(referral, event, request)

    def send(hospital):
        service = ReferralService(
            SynchronizedRepository(path), build_hospital_service()
        )
        try:
            return service.send_request(referral.referral_id, hospital, ACTOR)
        except ConflictError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(send, ["H01", "H06"]))
    assert sum(isinstance(result, ConflictError) for result in outcomes) == 1
    assert len(repository.list_requests(referral_id=referral.referral_id)) == 1
    assert len(repository.history(referral.referral_id)) == 2
    assert repository.get_referral(referral.referral_id).version == 1


def test_foreign_key_failure_rolls_back(persisted):
    _, repository, _, referral = persisted
    invalid = Referral.model_validate(
        {
            **referral.model_dump(),
            "status": "awaiting_hospital",
            "selected_request_id": "missing-request",
            "version": 1,
        }
    )
    event = ReferralEvent(
        event_id=str(uuid4()),
        referral_id=referral.referral_id,
        action="request_sent",
        actor_id=ACTOR.actor_id,
        actor_role=ACTOR.role,
        timestamp=datetime.now(UTC),
        version=1,
        details={},
    )
    with pytest.raises(PersistenceError, match="FOREIGN KEY"):
        repository.save_transition(invalid, event)
    assert repository.get_referral(referral.referral_id) == referral
    assert len(repository.history(referral.referral_id)) == 1


def test_unique_active_request_constraint(persisted):
    _, repository, service, referral = persisted
    request = service.send_request(referral.referral_id, "H01", ACTOR)
    current = repository.get_referral(referral.referral_id)
    second = HospitalRequest.model_validate(
        {
            **request.model_dump(),
            "request_id": str(uuid4()),
            "hospital_id": "H06",
        }
    )
    updated = Referral.model_validate(
        {
            **current.model_dump(),
            "selected_request_id": second.request_id,
            "version": 2,
        }
    )
    event = ReferralEvent(
        event_id=str(uuid4()),
        referral_id=referral.referral_id,
        action="request_sent",
        actor_id=ACTOR.actor_id,
        actor_role=ACTOR.role,
        timestamp=datetime.now(UTC),
        version=2,
        details={},
    )
    with pytest.raises(PersistenceError, match="UNIQUE"):
        repository.save_transition(updated, event, second)
    assert repository.get_referral(referral.referral_id) == current
    assert repository.list_requests(referral_id=referral.referral_id) == (request,)
    assert len(repository.history(referral.referral_id)) == 2


def test_parameterized_identifiers(persisted):
    _, repository, service, referral = persisted
    assert repository.get_referral("' OR 1=1 --") is None
    assert repository.get_request("'; DROP TABLE referrals; --") is None
    assert service.get_referral(referral.referral_id) == referral
