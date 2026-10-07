import argparse

from siamcare.commands.actors import add_actor_arguments, demo_actor
from siamcare.services.referral_service import ReferralService


def add_commands(groups) -> None:
    requests = groups.add_parser(
        "requests", help="Record local simulated hospital requests"
    )
    commands = requests.add_subparsers(dest="command", required=True)
    listing = commands.add_parser(
        "list", help="List requests including historical responses"
    )
    filters = listing.add_mutually_exclusive_group(required=True)
    filters.add_argument("--referral", dest="referral_id")
    filters.add_argument("--hospital", dest="hospital_id")
    send = commands.add_parser(
        "send", help="Record a request locally; no hospital is contacted"
    )
    send.add_argument("referral_id")
    send.add_argument("--hospital", required=True, dest="hospital_id")
    add_actor_arguments(send)
    for name in ("accept", "decline"):
        command = commands.add_parser(name, help=f"Simulate hospital {name}")
        command.add_argument("request_id")
        command.add_argument("--reason", required=name == "decline")
        add_actor_arguments(command)


def execute(args: argparse.Namespace, service: ReferralService):
    if args.command == "list":
        return service.list_requests(
            referral_id=args.referral_id, hospital_id=args.hospital_id
        )
    if args.command == "send":
        return service.send_request(
            args.referral_id, args.hospital_id, demo_actor(args)
        )
    return service.respond_to_request(
        args.request_id,
        demo_actor(args),
        accept=args.command == "accept",
        reason=args.reason,
    )
