from typing import Protocol

from siamcare.models.hospital import Hospital


class HospitalRepository(Protocol):
    def list_hospitals(self) -> tuple[Hospital, ...]: ...

    def get_hospital(self, hospital_id: str) -> Hospital | None: ...
