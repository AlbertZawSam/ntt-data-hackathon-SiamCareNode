"""CLI entry point: parse, compose, dispatch and present expected application errors."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from siamcare.commands import hospitals, referrals, requests
from siamcare.composition import build_hospital_service, build_referral_service
from siamcare.errors import ApplicationError, NotFoundError
from siamcare.presentation import render_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SiamCareNode local synthetic demo")
    parser.add_argument(
        "--dataset", type=Path, help="Hospital JSON path (before command group)"
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Override SIAMCARE_DATABASE_PATH from the environment or .env",
    )
    groups = parser.add_subparsers(dest="group", required=True)
    for command_module in (hospitals, referrals, requests):
        command_module.add_commands(groups)
    args = parser.parse_args(argv)

    try:
        hospital_service = build_hospital_service(args.dataset)
        if args.group == "hospitals":
            result = hospitals.execute(args, hospital_service)
        else:
            service = build_referral_service(hospital_service, args.database)
            handler = referrals if args.group == "referrals" else requests
            result = handler.execute(args, service)
    except NotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (ApplicationError, ValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.group != "hospitals":
        print(
            "LOCAL SIMULATION: requests are recorded only; no hospital is contacted. "
            "Actor flags are not authentication. Approval records a decision only; "
            "no beds are reserved and no transport starts.",
            file=sys.stderr,
        )
    print("Recorded bed snapshots do not guarantee admission.", file=sys.stderr)
    print(render_json(result))
    return 0
