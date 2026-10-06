from siamcare.models.hospital import Hospital, normalize_specialty
from siamcare.repositories.hospital_repository import HospitalRepository


class HospitalNotFoundError(LookupError):
    """The requested hospital ID does not exist."""


class HospitalService:
    def __init__(self, repository: HospitalRepository) -> None:
        self._repository = repository

    def list_hospitals(self) -> tuple[Hospital, ...]:
        return tuple(
            sorted(self._repository.list_hospitals(), key=lambda h: h.hospital_id)
        )

    def get_hospital(self, hospital_id: str) -> Hospital:
        hospital = self._repository.get_hospital(hospital_id)
        if hospital is None:
            raise HospitalNotFoundError(f"Hospital {hospital_id!r} not found")
        return hospital

    def search_hospitals(
        self, specialty: str, min_free_beds: int | None = None
    ) -> tuple[Hospital, ...]:
        if min_free_beds is not None and (
            type(min_free_beds) is not int or min_free_beds < 0
        ):
            raise ValueError("min_free_beds must be a nonnegative integer")
        specialty = normalize_specialty(specialty)
        return tuple(
            hospital
            for hospital in self.list_hospitals()
            if specialty in hospital.specialties
            and (min_free_beds is None or hospital.free_beds >= min_free_beds)
        )
