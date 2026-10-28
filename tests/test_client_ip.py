"""Visitor IP behind the Cloudflare Tunnel (no database needed)."""

import pytest
from starlette.requests import Request

from dbresearch.auth import client_ip
from dbresearch.config import get_settings


def request(headers: dict[str, str], peer: str = "172.24.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


@pytest.fixture
def trusted(monkeypatch):
    def use(header: str | None):
        if header:
            monkeypatch.setenv("TRUSTED_IP_HEADER", header)
        else:
            monkeypatch.delenv("TRUSTED_IP_HEADER", raising=False)
        get_settings.cache_clear()

    yield use
    get_settings.cache_clear()


def test_peer_address_without_a_trusted_header(trusted):
    trusted(None)
    assert client_ip(request({"CF-Connecting-IP": "203.0.113.9"})) == "172.24.0.1"


def test_cloudflare_header_wins_when_trusted(trusted):
    trusted("CF-Connecting-IP")
    assert client_ip(request({"CF-Connecting-IP": " 203.0.113.9 "})) == "203.0.113.9"
    assert client_ip(request({"CF-Connecting-IP": "2001:db8::1"})) == "2001:db8::1"
    assert client_ip(request({})) == "172.24.0.1"  # header missing: SSH-tunnel access
    assert client_ip(request({"CF-Connecting-IP": "not-an-ip"})) is None
