from typing import Protocol

from siamcare.models.referral import HospitalRequest, Referral, ReferralEvent


class ReferralRepository(Protocol):
    def get_referral(self, referral_id: str) -> Referral | None: ...

    def list_referrals(self) -> tuple[Referral, ...]: ...

    def get_request(self, request_id: str) -> HospitalRequest | None: ...

    def list_requests(
        self, *, referral_id: str | None = None, hospital_id: str | None = None
    ) -> tuple[HospitalRequest, ...]: ...

    def history(self, referral_id: str) -> tuple[ReferralEvent, ...]: ...

    def create(self, referral: Referral, event: ReferralEvent) -> None:
        """Persist the new referral and its initial event atomically."""
        ...

    def save_transition(
        self,
        referral: Referral,
        event: ReferralEvent,
        request: HospitalRequest | None = None,
    ) -> None:
        """Atomically save state, optional request and event only at version - 1.

        A DynamoDB adapter needs conditional transactional writes for this contract;
        independent put operations cannot safely replace SQLite transactions.
        """
        ...
