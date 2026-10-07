import argparse

from siamcare.services.hospital_service import HospitalService


def add_commands(groups) -> None:
    hospitals = groups.add_parser("hospitals", help="Discover synthetic hospitals")
    commands = hospitals.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List all hospitals")
    get = commands.add_parser("get", help="Get one hospital by ID")
    get.add_argument("hospital_id")
    search = commands.add_parser("search", help="Match an explicit specialty")
    search.add_argument("--specialty", required=True)
    search.add_argument("--min-free-beds", type=int)


def execute(args: argparse.Namespace, service: HospitalService):
    if args.command == "get":
        return service.get_hospital(args.hospital_id)
    if args.command == "list":
        return service.list_hospitals()
    return service.search_hospitals(args.specialty, args.min_free_beds)
