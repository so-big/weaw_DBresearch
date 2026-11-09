"""University login pieces that need no database."""

import pytest

from dbresearch.auth import get_provider
from dbresearch.config import get_settings
from dbresearch.university import HttpUniversityClient


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
