"""Login with a university account, checked by the university's login API.

PLACEHOLDER: the API spec has not arrived yet. Only `HttpUniversityClient.verify` should need
changing once it does (URL, request body, response fields). Everything else (who may log
in, account linking, audit, rate limits, sessions) is final.

Rules:
- The password is sent to the API only, over HTTPS, and never stored or logged.
- Only account types in `university_allowed_types` (default: staff) may log in: the
  research office staff who manage the papers. Teachers don't log in: they get share links
  (guests, no account). Students never get in.
- Roles stay in our DB. A new account starts as `user`; ADMIN promotes.
- A first login that matches nobody ADMIN added becomes a *pending* request (DESIGN §1, §9):
  no access until ADMIN approves it. Departments in `university_auto_approve_departments`
  skip the queue (only once the API returns the department).
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from dbresearch import audit
from dbresearch.auth import (
    Credentials,
    LoginPending,
    LoginRejected,
    ProviderUnavailable,
    active_user,
    normalize_username,
)
from dbresearch.config import get_settings
from dbresearch.models import AuthIdentity, User, UserRole, UserStatus
from dbresearch.search_text import compact

PROVIDER = "university"


@dataclass(frozen=True)
class UniversityAccount:
    subject: str  # the university ID (staff or student number)
    account_type: str  # e.g. "staff", "teacher", "student", lower-cased
    display_name: str | None = None
    email: str | None = None
    department: str | None = None  # if the API gives it (not known yet)


class UniversityClient(Protocol):
    def verify(self, username: str, password: str) -> UniversityAccount | None:
        """The account, or None for a wrong ID or password.
        Raise ProviderUnavailable when the API can't answer."""
        ...


class HttpUniversityClient:
    """Calls the university login API. PLACEHOLDER request/response shape:

    POST <url>  {"username": ..., "password": ...}
    200 -> {"ok": true, "id": "...", "type": "staff", "name": "...", "email": "...",
            "department": "..."}
    200 {"ok": false} or 401/403 -> wrong ID or password
    """

    def __init__(self, url: str, api_key: str | None, timeout: float):
        parsed = urlparse(url)
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise RuntimeError("UNIVERSITY_API_URL must use https://")
        self.url, self.api_key, self.timeout = url, api_key, timeout

    def verify(self, username: str, password: str) -> UniversityAccount | None:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.url,
            data=json.dumps({"username": username, "password": password}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403, 404):
                return None
            raise ProviderUnavailable(f"HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            # No details: an exception chain could carry the request body.
            raise ProviderUnavailable(type(exc).__name__) from None
        if not isinstance(data, dict) or not data.get("ok") or not data.get("id"):
            return None
        return UniversityAccount(
            subject=str(data["id"]).strip(),
            account_type=str(data.get("type") or "").strip().lower(),
            display_name=(data.get("name") or None),
            email=(data.get("email") or None),
            department=(str(data.get("department") or "").strip() or None),
        )


# Student usernames (DESIGN §9): an 8-digit student ID (entry year + faculty + running no.),
# or an email local part ending in the 2-digit entry year (`somchaij68`). Staff and teachers
# use first name + surname initial with no digits, so they can't be told apart here.
_STUDENT_USERNAME = re.compile(r"\d{8}|[a-z]+\d{2}")


def local_part(username: str) -> str:
    return username.strip().lower().split("@", 1)[0]


def is_student_username(username: str) -> bool:
    return _STUDENT_USERNAME.fullmatch(local_part(username)) is not None


class PhpLdapTestClient:
    """TEST ONLY: IT's `RealLogin.php` (LDAP bind against the university AD).

    POST username=<local part>&password=...  (the script adds `@nu.local` itself)
    "Login successful" -> right password; "wrong user or password" -> wrong.

    The script returns no ID, account type or department, so every non-student login is
    reported as type "staff" and our users table decides: someone ADMIN added (same email or
    university ID) logs in, anyone else becomes a pending request. The script logs anyone in
    with an empty password, so blank passwords never reach it.
    """

    def __init__(self, url: str, email_domain: str, timeout: float):
        if urlparse(url).scheme not in ("http", "https"):
            raise RuntimeError("UNIVERSITY_API_URL must be http(s)://")
        self.url, self.email_domain, self.timeout = url, email_domain, timeout

    def verify(self, username: str, password: str) -> UniversityAccount | None:
        user = local_part(username)
        if not user or not password.strip():
            return None
        request = urllib.request.Request(
            self.url,
            data=urlencode({"username": user, "password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read(4096).decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No details: an exception chain could carry the request body.
            raise ProviderUnavailable(type(exc).__name__) from None
        if "login successful" in text.lower():
            return UniversityAccount(
                subject=user, account_type="staff", email=f"{user}@{self.email_domain}"
            )
        if "wrong user or password" in text.lower():
            return None
        raise ProviderUnavailable("unexpected reply")


class UniversityApiProvider:
    name = PROVIDER

    def __init__(
        self,
        client: UniversityClient,
        allowed_types: set[str],
        auto_approve_departments: set[str] = frozenset(),
    ):
        self.client = client
        self.allowed_types = {t.strip().lower() for t in allowed_types if t.strip()}
        self.auto_approve = {compact(d) for d in auto_approve_departments if d.strip()}

    @classmethod
    def from_settings(cls) -> "UniversityApiProvider":
        settings = get_settings()
        if not settings.university_api_url:
            raise RuntimeError("AUTH_PROVIDERS has 'university' but UNIVERSITY_API_URL is unset")
        client: UniversityClient
        if settings.university_client == "php_ldap_test":
            client = PhpLdapTestClient(
                settings.university_api_url,
                settings.university_email_domain,
                settings.university_api_timeout_seconds,
            )
        elif settings.university_client == "api":
            client = HttpUniversityClient(
                settings.university_api_url,
                settings.university_api_key,
                settings.university_api_timeout_seconds,
            )
        else:
            raise RuntimeError(f"Unknown UNIVERSITY_CLIENT: {settings.university_client!r}")
        return cls(
            client,
            set(settings.university_allowed_types.split(",")),
            set(settings.university_auto_approve_departments.split(",")),
        )

    def authenticate(self, db: Session, credentials: Credentials) -> User:
        username = normalize_username(credentials.username)
        if is_student_username(username):
            # Refused before the password goes anywhere.
            raise LoginRejected("type_not_allowed:student")
        account = self.client.verify(username, credentials.password)
        if account is None:
            raise LoginRejected("wrong_password")
        if account.account_type not in self.allowed_types:
            raise LoginRejected(f"type_not_allowed:{account.account_type or 'unknown'}")
        identity = db.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == PROVIDER, AuthIdentity.subject == account.subject
            )
        )
        if identity is not None:
            return active_user(db, identity.user_id)
        return self._link_or_create(db, account)

    def _link_or_create(self, db: Session, account: UniversityAccount) -> User:
        """First login: attach to a user ADMIN added with the same email, or file a request."""
        user = db.scalar(select(User).where(User.email == account.email)) if account.email else None
        if user is not None:
            active_user(db, user.id)
            db.add(AuthIdentity(user_id=user.id, provider=PROVIDER, subject=account.subject))
            db.flush()
            return user
        approved = bool(account.department) and compact(account.department) in self.auto_approve
        user = User(
            email=account.email or f"{account.subject}@university.invalid",
            display_name=account.display_name or account.subject,
            role=UserRole.USER,
            status=UserStatus.ACTIVE if approved else UserStatus.PENDING,
        )
        db.add(user)
        db.flush()
        db.add(AuthIdentity(user_id=user.id, provider=PROVIDER, subject=account.subject))
        audit.record(
            db,
            "user.create" if approved else "user.request",
            "user",
            user.id,
            actor_id=user.id,
            via=PROVIDER,
            account_type=account.account_type,
            department=account.department,
            role=UserRole.USER.value,
            **({"auto_approved": True} if approved else {}),
        )
        db.flush()
        if not approved:
            raise LoginPending()
        return user


def add_university_identity(db: Session, user: User, university_id: str) -> AuthIdentity:
    """ADMIN pre-registers someone by their university ID (skips the approval queue)."""
    identity = AuthIdentity(user_id=user.id, provider=PROVIDER, subject=university_id.strip())
    db.add(identity)
    return identity
