"""Operator commands, run inside the api container:

    docker compose exec api python -m dbresearch.cli create-admin \
        --email a@example.org --name "A" --username a

The password is read from DBR_PASSWORD or prompted; it is never a command-line argument.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from dbresearch import audit
from dbresearch.auth import add_local_identity, normalize_username
from dbresearch.db import new_session
from dbresearch.models import AuthIdentity, User, UserRole


def _read_password() -> str:
    password = os.environ.get("DBR_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < 10:
        sys.exit("Password must be at least 10 characters")
    return password


def create_user(args: argparse.Namespace, role: UserRole) -> None:
    with new_session() as db:
        username = normalize_username(args.username)
        taken = db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local", AuthIdentity.subject == username
            )
        )
        if taken or db.scalar(select(User).where(User.email == args.email)):
            sys.exit("A user with that username or email already exists")
        user = User(email=args.email, display_name=args.name, role=role)
        db.add(user)
        db.flush()
        add_local_identity(db, user, username, _read_password())
        audit.record(db, "user.create", "user", user.id, via="cli", role=role.value)
        db.commit()
        print(f"Created {role.value} {username} ({user.id})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dbresearch.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "create-user"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--email", required=True)
        cmd.add_argument("--name", required=True)
        cmd.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        create_user(args, UserRole.ADMIN)
    elif args.command == "create-user":
        create_user(args, UserRole.USER)


if __name__ == "__main__":
    main()
