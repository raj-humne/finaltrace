"""Operator CLI. `python -m api.cli create-user` prompts for a password —
never accepts one as a command-line argument, since that would land in shell
history and process listings.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

import api.models  # noqa: F401  (register all tables on Base.metadata)
from api.db.base import Base
from api.db.session import SessionLocal, engine
from api.models.identity import ACCOUNT_ROLES, Account
from api.security.passwords import hash_password


def create_user(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m api.cli create-user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", required=True, choices=ACCOUNT_ROLES)
    args = parser.parse_args(argv)

    Base.metadata.create_all(engine)

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords did not match.", file=sys.stderr)
        return 1
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        existing = db.scalar(select(Account).where(Account.username == args.username))
        if existing is not None:
            print(f"Account '{args.username}' already exists.", file=sys.stderr)
            return 1

        account = Account(
            username=args.username,
            display_name=args.display_name,
            role=args.role,
            password_hash=hash_password(password),
        )
        db.add(account)
        db.commit()
        print(f"Created account '{args.username}' with role '{args.role}'.")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "create-user":
        print("usage: python -m api.cli create-user --username U --display-name N --role R", file=sys.stderr)
        return 2
    return create_user(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
