import os

import pytest
from fastapi.testclient import TestClient

from dbresearch.main import app

client = TestClient(app)


def test_health_reports_every_check():
    body = client.get("/health").json()
    assert {"database", "blob_store"} <= body["checks"].keys()
    assert body["status"] in {"ok", "degraded"}


@pytest.mark.db
@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs the compose stack")
def test_health_ok_on_stack():
    response = client.get("/health")
    assert response.status_code == 200, response.json()
    assert response.json()["checks"]["db_locale"] == "ok"
