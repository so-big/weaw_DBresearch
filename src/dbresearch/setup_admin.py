"""Idempotent admin setup from setting.txt, arguments, or environment variables."""
import sys
from pathlib import Path
from sqlalchemy import select

from dbresearch.auth import add_local_identity, hash_password, normalize_username
from dbresearch.db import new_session
from dbresearch.models import AuthIdentity, User, UserRole
from dbresearch.settings_parser import get_web_credentials


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
    target_file = None
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg in ("--root", "--setting", "-c") and i + 1 < len(argv):
            target_file = Path(argv[i + 1])
            break

    _, username, password = get_web_credentials(target_file)
    ensure_admin(username, password)


if __name__ == "__main__":
    main()
