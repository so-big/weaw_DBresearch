"""Share-link tokens never reach the HTTP access log."""

import logging

from dbresearch.main import RedactShareTokens


def access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.1:5000", "GET", path, "1.1", 200),
        None,
    )


def test_share_tokens_are_redacted():
    for path, shown in (
        ("/api/s/AbC-123_xyz/file?download=1", "/api/s/…/file?download=1"),
        ("/s/AbC-123_xyz", "/s/…"),
        ("/api/documents/42/file", "/api/documents/42/file"),
    ):
        record = access_record(path)
        assert RedactShareTokens().filter(record)
        assert record.getMessage() == f'10.0.0.1:5000 - "GET {shown} HTTP/1.1" 200'
