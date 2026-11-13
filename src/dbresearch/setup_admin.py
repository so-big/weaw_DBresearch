"""Idempotent admin setup from root.txt, arguments, or environment variables."""
import os
import sys
from pathlib import Path
from sqlalchemy import select

from dbresearch.auth import add_local_identity, hash_password, normalize_username
from dbresearch.db import new_session
from dbresearch.models import AuthIdentity, User, UserRole


def get_credentials(argv: list[str]) -> tuple[str, str]:
    # 1. Check CLI args for --root <path>
    filepath = None
    for i, arg in enumerate(argv):
        if arg == "--root" and i + 1 < len(argv):
            filepath = Path(argv[i + 1])
            break

    # 2. Check env var ROOT_FILE or CREDENTIALS_FILE
    if not filepath:
        env_path = os.environ.get("ROOT_FILE") or os.environ.get("CREDENTIALS_FILE")
        if env_path:
            filepath = Path(env_path)

    # 3. Check default root.txt candidates
    if not filepath:
        for candidate in [Path("root.txt"), Path("/app/root.txt"), Path("/root.txt")]:
            if candidate.is_file():
                filepath = candidate
                break

    username = os.environ.get("ADMIN_USERNAME") or os.environ.get("ROOT_USER")
    password = os.environ.get("ADMIN_PASSWORD") or os.environ.get("ROOT_PASSWORD")

    if filepath and filepath.is_file():
        try:
            lines = [line.strip() for line in filepath.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            if len(lines) >= 1 and not username:
                username = lines[0]
            if len(lines) >= 2 and not password:
                password = lines[1]
        except Exception as exc:
            print(f"[WARN] Failed to read credentials from {filepath}: {exc}", file=sys.stderr)

    username = username or "admin"
    password = password or "admin123456"
    return username, password


def ensure_admin(username: str, password: str, email: str | None = None, display_name: str | None = None) -> None:
    norm_user = normalize_username(username)
    email = email or f"{norm_user}@dbresearch.local"
    display_name = display_name or username.capitalize()

    with new_session() as db:
        identity = db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.subject == norm_user,
            )
        )
        if identity:
            identity.password_hash = hash_password(password)
            user = db.get(User, identity.user_id)
            if user:
                user.role = UserRole.ADMIN
            db.commit()
            print(f"[OK] Admin user '{norm_user}' password updated successfully.")
        else:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, display_name=display_name, role=UserRole.ADMIN)
                db.add(user)
                db.flush()
            add_local_identity(db, user, norm_user, password)
            db.commit()
            print(f"[OK] Admin user '{norm_user}' created successfully.")


def main():
    username, password = get_credentials(sys.argv[1:])
    ensure_admin(username, password)


if __name__ == "__main__":
    main()
