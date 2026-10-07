import argparse

from siamcare.commands.actors import add_actor_arguments, demo_actor
from siamcare.models.referral import CreateReferral, Urgency
from siamcare.services.referral_service import ReferralService


def add_commands(groups) -> None:
    referrals = groups.add_parser("referrals", help="Local simulated referral workflow")
    commands = referrals.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a synthetic referral")
    create.add_argument(
        "--patient", required=True, help="Synthetic reference only; no names"
    )
    create.add_argument("--specialty", required=True)
    create.add_argument("--urgency", required=True, choices=list(Urgency))
    add_actor_arguments(create)
    commands.add_parser("list", help="List persisted referrals")
    for name, help_text in [
        ("get", "Show referral status and selected request ID"),
        (
            "hospitals",
            "Find exact specialty matches with at least one recorded free bed",
        ),
        ("history", "Show ordered events"),
        ("submit-review", "Submit the accepted request for physician review"),
        (
            "approve",
            "Record a simulated physician approval; no reservation or dispatch",
        ),
        ("reject", "Record a terminal simulated physician rejection"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("referral_id")
        if name in {"submit-review", "approve", "reject"}:
            add_actor_arguments(command)
        if name in {"approve", "reject"}:
            command.add_argument("--reason", required=name == "reject")


def execute(args: argparse.Namespace, service: ReferralService):
    match args.command:
        case "create":
            data = CreateReferral(
                patient_reference=args.patient,
                specialty=args.specialty,
                urgency=args.urgency,
            )
            return service.create_referral(data, demo_actor(args))
        case "list":
            return service.list_referrals()
        case "get":
            return service.get_referral(args.referral_id)
        case "hospitals":
            return service.find_hospitals(args.referral_id)
        case "history":
            return service.history(args.referral_id)
        case "submit-review":
            return service.submit_for_review(args.referral_id, demo_actor(args))
        case "approve" | "reject":
            return service.decide_referral(
                args.referral_id,
                demo_actor(args),
                approve=args.command == "approve",
                reason=args.reason,
            )
    raise AssertionError(f"Unhandled referral command: {args.command}")
