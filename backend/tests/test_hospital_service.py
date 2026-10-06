import pytest

from siamcare.models.hospital import Hospital
from siamcare.services.hospital_service import HospitalNotFoundError, HospitalService


class MemoryRepository:
    def __init__(self, hospitals):
        self.hospitals = hospitals

    def list_hospitals(self):
        return self.hospitals

    def get_hospital(self, hospital_id):
        return next((h for h in self.hospitals if h.hospital_id == hospital_id), None)


@pytest.fixture
def service(record):
    hospitals = tuple(
        Hospital.model_validate(
            {
                **record,
                "hospital_id": hospital_id,
                "free_beds": beds,
                "specialties": specialties,
            }
        )
        for hospital_id, beds, specialties in [
            ("H03", 2, ["neurology"]),
            ("H02", 0, ["neurology"]),
            ("H04", 5, ["cardiology"]),
            ("H01", 1, [" Neurology "]),
        ]
    )
    return HospitalService(MemoryRepository(hospitals))


@pytest.mark.parametrize("specialty", ["neurology", "NEUROLOGY", " NeuRoLogy \t"])
def test_specialty_normalization(service, specialty):
    assert [h.hospital_id for h in service.search_hospitals(specialty)] == [
        "H01",
        "H02",
        "H03",
    ]


@pytest.mark.parametrize(
    ("minimum", "expected"),
    [
        (None, ["H01", "H02", "H03"]),
        (0, ["H01", "H02", "H03"]),
        (1, ["H01", "H03"]),
        (2, ["H03"]),
        (3, []),
    ],
)
def test_capacity_filter(service, minimum, expected):
    assert [
        h.hospital_id for h in service.search_hospitals("neurology", minimum)
    ] == expected


@pytest.mark.parametrize("specialty", ["", "  ", "neuro", "stroke", "unknown"])
def test_empty_and_explicit_matching(service, specialty):
    assert service.search_hospitals(specialty) == ()


@pytest.mark.parametrize("minimum", [-1, 1.5, True, "1"])
def test_invalid_minimum(service, minimum):
    with pytest.raises(ValueError, match="nonnegative integer"):
        service.search_hospitals("neurology", minimum)


def test_list_get_and_unknown(service):
    assert [h.hospital_id for h in service.list_hospitals()] == [
        "H01",
        "H02",
        "H03",
        "H04",
    ]
    assert service.get_hospital("H02").free_beds == 0
    with pytest.raises(HospitalNotFoundError, match="'missing' not found"):
        service.get_hospital("missing")


def test_empty_repository():
    service = HospitalService(MemoryRepository(()))
    assert service.list_hospitals() == ()
    assert service.search_hospitals("neurology") == ()
