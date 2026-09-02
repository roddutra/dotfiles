#!/usr/bin/env python3
"""Generate cryptographically random alphanumeric seeds for design exploration."""

from __future__ import annotations

import argparse
import json
import secrets
import string

ALPHABET = string.ascii_letters + string.digits


def bounded_int(value: str, *, minimum: int, maximum: int, name: str) -> int:
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate random alphanumeric design seeds."
    )
    parser.add_argument(
        "--count",
        type=lambda value: bounded_int(value, minimum=1, maximum=20, name="count"),
        default=1,
        help="Number of seeds to generate (default: 1).",
    )
    parser.add_argument(
        "--length",
        type=lambda value: bounded_int(value, minimum=16, maximum=256, name="length"),
        default=48,
        help="Characters per seed (default: 48).",
    )
    parser.add_argument(
        "--format",
        choices=("plain", "json"),
        default="plain",
        help="Output format (default: plain).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = [
        "".join(secrets.choice(ALPHABET) for _ in range(args.length))
        for _ in range(args.count)
    ]

    if args.format == "json":
        print(json.dumps({"seeds": seeds}, indent=2))
        return

    print("\n".join(seeds))


if __name__ == "__main__":
    main()
