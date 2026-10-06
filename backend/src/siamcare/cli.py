"""Argument parsing, dependency construction and JSON presentation."""

import argparse
import json
import sys
from importlib.resources import as_file, files
from pathlib import Path

from siamcare.repositories.json_hospital_repository import (
    HospitalDataError,
    JsonHospitalRepository,
)
from siamcare.services.hospital_service import HospitalNotFoundError, HospitalService


def default_dataset_path() -> Path:
    """Resolve the source checkout default independently of the working directory."""
    return Path(__file__).resolve().parents[2] / "data" / "mock" / "hospitals.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SiamCareNode hospital discovery")
    parser.add_argument("--dataset", type=Path, help="Path to a hospital JSON array")
    groups = parser.add_subparsers(dest="group", required=True)
    hospitals = groups.add_parser("hospitals")
    commands = hospitals.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    get = commands.add_parser("get")
    get.add_argument("hospital_id")
    search = commands.add_parser("search")
    search.add_argument("--specialty", required=True)
    search.add_argument("--min-free-beds", type=int)
    args = parser.parse_args(argv)

    try:
        path = args.dataset if args.dataset is not None else default_dataset_path()
        if args.dataset is None and not path.is_file():
            # Wheels include the same fixture as package data.
            resource = files("siamcare").joinpath("data/mock/hospitals.json")
            with as_file(resource) as bundled_path:
                repository = JsonHospitalRepository(bundled_path)
        else:
            repository = JsonHospitalRepository(path)
        service = HospitalService(repository)
        if args.command == "get":
            result = service.get_hospital(args.hospital_id).model_dump(mode="json")
        else:
            records = (
                service.list_hospitals()
                if args.command == "list"
                else service.search_hospitals(args.specialty, args.min_free_beds)
            )
            result = [hospital.model_dump(mode="json") for hospital in records]
    except HospitalNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (HospitalDataError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Recorded bed snapshots do not guarantee admission.", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
