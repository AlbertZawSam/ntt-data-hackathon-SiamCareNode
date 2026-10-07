"""Construct explicitly unverified demo identity at the CLI boundary."""

import argparse

from siamcare.models.referral import ActorContext, ActorRole


def add_actor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--actor", required=True, help="Synthetic demo actor ID (not login)"
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=list(ActorRole),
        help="Simulated role; these flags do not authenticate anyone",
    )
    parser.add_argument(
        "--actor-hospital", help="Required hospital scope for hospital_staff"
    )


def demo_actor(args: argparse.Namespace) -> ActorContext:
    # Future transports must construct this from verified identity, never client claims.
    return ActorContext(
        actor_id=args.actor, role=args.role, hospital_id=args.actor_hospital
    )
