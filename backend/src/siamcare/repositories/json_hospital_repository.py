"""Load an entire validated snapshot; never silently skip invalid records."""

import json
from pathlib import Path

from pydantic import ValidationError

from siamcare.models.hospital import Hospital


class HospitalDataError(ValueError):
    """A dataset cannot be read or violates the hospital schema."""


class JsonHospitalRepository:
    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HospitalDataError(
                f"Cannot load hospitals from {path}: {exc}"
            ) from exc
        if not isinstance(records, list):
            raise HospitalDataError(
                f"{path}: expected a JSON array of hospital records"
            )

        hospitals: dict[str, Hospital] = {}
        for index, record in enumerate(records):
            try:
                hospital = Hospital.model_validate(record)
            except ValidationError as exc:
                raise HospitalDataError(
                    f"{path}: invalid hospital record at index {index}: {exc}"
                ) from exc
            if hospital.hospital_id in hospitals:
                raise HospitalDataError(
                    f"{path}: duplicate hospital ID {hospital.hospital_id!r} "
                    f"at index {index}"
                )
            hospitals[hospital.hospital_id] = hospital
        self._hospitals = hospitals

    def list_hospitals(self) -> tuple[Hospital, ...]:
        return tuple(self._hospitals[key] for key in sorted(self._hospitals))

    def get_hospital(self, hospital_id: str) -> Hospital | None:
        return self._hospitals.get(hospital_id)
