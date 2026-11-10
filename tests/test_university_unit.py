"""University login pieces that need no database."""

import pytest

from dbresearch.auth import ProviderUnavailable, get_provider
from dbresearch.config import get_settings
from dbresearch.university import (
    HttpUniversityClient,
    PhpLdapTestClient,
    UniversityAccount,
    is_student_username,
)


@pytest.mark.parametrize("url", ["http://login.uni.example/api", "ftp://x"])
def test_api_url_must_be_https(url):
    with pytest.raises(RuntimeError, match="https"):
        HttpUniversityClient(url, None, 5)


def test_local_http_is_allowed_for_a_dev_stub():
    HttpUniversityClient("http://127.0.0.1:9000/login", None, 5)


def test_unknown_or_unconfigured_providers_fail_loudly(monkeypatch):
    for value, message in (("local,ldap", "Unknown"), ("university", "UNIVERSITY_API_URL")):
        monkeypatch.setenv("AUTH_PROVIDERS", value)
        monkeypatch.delenv("UNIVERSITY_API_URL", raising=False)
        get_settings.cache_clear()
        try:
            with pytest.raises(RuntimeError, match=message):
                get_provider()
        finally:
            monkeypatch.delenv("AUTH_PROVIDERS")
            get_settings.cache_clear()


@pytest.mark.parametrize(
    ("username", "student"),
    [
        ("68369999", True),
        ("somchaij68", True),
        ("SomchaiJ68@nu.ac.th", True),
        ("somchaij", False),
        ("somchaij@nu.ac.th", False),
        ("t1001", False),
        ("1234567", False),
    ],
)
def test_student_usernames_are_recognised(username, student):
    assert is_student_username(username) is student


class _Reply:
    def __init__(self, text: str):
        self.text = text.encode()

    def read(self, _n: int) -> bytes:
        return self.text

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _php_client(monkeypatch, reply: str) -> tuple[PhpLdapTestClient, list]:
    sent = []

    def fake_urlopen(request, timeout):
        sent.append(request)
        return _Reply(reply)

    monkeypatch.setattr("dbresearch.university.urllib.request.urlopen", fake_urlopen)
    return PhpLdapTestClient("http://reallogin-test/index.php", "nu.ac.th", 5), sent


def test_php_test_client_success_becomes_a_staff_account(monkeypatch):
    client, sent = _php_client(monkeypatch, "<p>Login successful!<br>")
    account = client.verify("SomchaiJ@nu.ac.th", "pw")
    assert account == UniversityAccount(
        subject="somchaij", account_type="staff", email="somchaij@nu.ac.th"
    )
    assert sent[0].data == b"username=somchaij&password=pw"


def test_php_test_client_wrong_password(monkeypatch):
    client, _ = _php_client(monkeypatch, "wrong user or password")
    assert client.verify("somchaij", "nope") is None


@pytest.mark.parametrize("password", ["", "   "])
def test_php_test_client_never_sends_a_blank_password(monkeypatch, password):
    client, sent = _php_client(monkeypatch, "<p>Login successful!<br>")
    assert client.verify("somchaij", password) is None
    assert sent == []


def test_php_test_client_odd_reply_is_an_outage(monkeypatch):
    client, _ = _php_client(monkeypatch, "Cannot connect to ldap://x")
    with pytest.raises(ProviderUnavailable):
        client.verify("somchaij", "pw")
