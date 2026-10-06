import pytest

from siamcare.repositories.json_hospital_repository import (
    HospitalDataError,
    JsonHospitalRepository,
)


def test_supplied_path_and_order(record, write_dataset):
    path = write_dataset([{**record, "hospital_id": "H02"}, record])
    repository = JsonHospitalRepository(str(path))
    assert [h.hospital_id for h in repository.list_hospitals()] == ["H01", "H02"]
    hospital = repository.get_hospital("H01")
    assert hospital.name_th == record["name_th"]
    assert hospital.capacity_updated_at.utcoffset().total_seconds() == 7 * 3600
    assert repository.get_hospital("missing") is None


@pytest.mark.parametrize(
    ("updates", "error"),
    [
        ({"total_beds": -1}, "total_beds"),
        ({"free_beds": -1}, "free_beds"),
        ({"free_beds": 11}, "cannot exceed"),
        ({"free_beds": True}, "free_beds"),
        ({"total_beds": 1.5}, "total_beds"),
        ({"free_beds": "2"}, "free_beds"),
        ({"capacity_updated_at": "2026-10-01T09:00:00"}, "timezone"),
        ({"capacity_updated_at": "yesterday"}, "capacity_updated_at"),
        ({"specialties": ["  "]}, "specialties"),
        ({"specialties": []}, "specialties"),
        ({"name_en": " "}, "name_en"),
        ({"hospital_id": ""}, "hospital_id"),
        ({"unexpected": 1}, "unexpected"),
    ],
)
def test_invalid_records(record, write_dataset, updates, error):
    with pytest.raises(HospitalDataError, match=error) as caught:
        JsonHospitalRepository(write_dataset([{**record, **updates}]))
    assert "index 0" in str(caught.value)
    assert "custom-hospitals.json" in str(caught.value)


def test_duplicate_ids(record, write_dataset):
    with pytest.raises(HospitalDataError, match="duplicate hospital ID 'H01'"):
        JsonHospitalRepository(
            write_dataset([record, {**record, "hospital_id": " H01 "}])
        )


@pytest.mark.parametrize("records", [{}, None, [None], [{}], ["invalid"]])
def test_malformed_shape(write_dataset, records):
    with pytest.raises(HospitalDataError):
        JsonHospitalRepository(write_dataset(records))


@pytest.mark.parametrize("contents", [b"{bad json", b"\xff"])
def test_invalid_file(tmp_path, contents):
    path = tmp_path / "bad.json"
    path.write_bytes(contents)
    with pytest.raises(HospitalDataError, match="Cannot load hospitals"):
        JsonHospitalRepository(path)


def test_missing_file(tmp_path):
    with pytest.raises(HospitalDataError, match="Cannot load hospitals"):
        JsonHospitalRepository(tmp_path / "missing.json")


def test_empty_dataset(write_dataset):
    assert JsonHospitalRepository(write_dataset([])).list_hospitals() == ()


def test_zero_total_beds_and_normalized_specialties(record, write_dataset):
    hospital = JsonHospitalRepository(
        write_dataset(
            [
                {
                    **record,
                    "total_beds": 0,
                    "free_beds": 0,
                    "specialties": [" Neurology ", "NEUROLOGY"],
                }
            ]
        )
    ).get_hospital("H01")
    assert hospital.specialties == ("neurology",)
    assert hospital.free_beds == 0
