"""Local adapter selection; future Lambda entry points can wire AWS adapters."""

from importlib.resources import as_file, files
from pathlib import Path

from siamcare.config import database_path
from siamcare.repositories.json_hospital_repository import JsonHospitalRepository
from siamcare.repositories.sqlite_referral_repository import SqliteReferralRepository
from siamcare.services.hospital_service import HospitalService
from siamcare.services.referral_service import ReferralService


def default_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "mock" / "hospitals.json"


def build_hospital_service(dataset: Path | None = None) -> HospitalService:
    path = dataset if dataset is not None else default_dataset_path()
    if dataset is None and not path.is_file():
        with as_file(files("siamcare").joinpath("data/mock/hospitals.json")) as bundled:
            repository = JsonHospitalRepository(bundled)
    else:
        repository = JsonHospitalRepository(path)
    return HospitalService(repository)


def build_referral_service(
    hospitals: HospitalService, database: Path | None = None
) -> ReferralService:
    path = database if database is not None else database_path()
    return ReferralService(SqliteReferralRepository(path), hospitals)
