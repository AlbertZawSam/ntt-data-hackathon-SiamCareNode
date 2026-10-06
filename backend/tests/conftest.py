import json

import pytest


@pytest.fixture
def record():
    return {
        "hospital_id": "H01",
        "name_en": "Synthetic Hospital",
        "name_th": "โรงพยาบาลจำลอง",
        "specialties": ["neurology"],
        "total_beds": 10,
        "free_beds": 2,
        "capacity_updated_at": "2026-10-01T09:00:00+07:00",
    }


@pytest.fixture
def write_dataset(tmp_path):
    def write(records):
        path = tmp_path / "custom-hospitals.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        return path

    return write
