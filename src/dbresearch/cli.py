"""Operator commands, run inside the api container:

    docker compose exec api python -m dbresearch.cli create-admin \
        --email a@example.org --name "A" --username a

The password is read from DBR_PASSWORD or prompted; it is never a command-line argument.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from sqlalchemy import select

from dbresearch import audit
from dbresearch.auth import add_local_identity, normalize_username
from dbresearch.crypto import generate_kek_json
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


def kek_init(out: Path) -> None:
    """Create the master key (KEK). Losing it makes every stored file unreadable: back it up
    to two places outside the server, separately from the data backups (docs/OPERATIONS.md)."""
    if out.exists():
        sys.exit(f"{out} already exists; refusing to overwrite the master key")
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(generate_kek_json())
    print(f"Wrote new KEK to {out}. Back it up NOW (two copies, outside the server).")


def verify_storage(sample: int | None) -> None:
    """Check every (or a random sample of) stored version: blob present, decrypts with the
    KEK, and matches its recorded SHA-256. Prints counts only, never content."""
    import hashlib
    import random

    from dbresearch.blobstore import get_blobstore
    from dbresearch.documents import read_version
    from dbresearch.models import DocumentVersion

    with new_session() as db:
        versions = list(db.scalars(select(DocumentVersion)))
    store = get_blobstore()
    missing = [v for v in versions if not store.exists(v.storage_key)]
    present = [v for v in versions if store.exists(v.storage_key)]
    checked = present if sample is None else random.sample(present, min(sample, len(present)))
    bad = []
    for version in checked:
        digest = hashlib.sha256()
        try:
            for chunk in read_version(version):
                digest.update(chunk)
        except Exception as exc:  # report and continue: we want the full picture
            bad.append(f"{version.id}: {type(exc).__name__}")
            continue
        if digest.digest() != version.sha256_plain:
            bad.append(f"{version.id}: hash mismatch")
    print(
        f"versions={len(versions)} missing_blobs={len(missing)} "
        f"decrypted={len(checked)} failed={len(bad)}"
    )
    for line in [f"{v.id}: blob missing" for v in missing] + bad:
        print("  " + line)
    if missing or bad:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dbresearch.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "create-user"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--email", required=True)
        cmd.add_argument("--name", required=True)
        cmd.add_argument("--username", required=True)
    kek = commands.add_parser("kek-init", help="create the master encryption key")
    kek.add_argument("--out", type=Path, required=True)
    verify = commands.add_parser("verify-storage", help="check blobs exist and decrypt")
    verify.add_argument("--sample", type=int, help="decrypt only N random versions")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        create_user(args, UserRole.ADMIN)
    elif args.command == "create-user":
        create_user(args, UserRole.USER)
    elif args.command == "kek-init":
        kek_init(args.out)
    elif args.command == "verify-storage":
        verify_storage(args.sample)


if __name__ == "__main__":
    main()
