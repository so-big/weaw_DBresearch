"""Serving the built web app next to the API (no database needed)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dbresearch.main import mount_web


def make_app(tmp_path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    (tmp_path / "assets" / "app-1a2b.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("nope")
    app = FastAPI()

    @app.get("/api/ping")
    def ping() -> dict:
        return {"ok": True}

    mount_web(app, tmp_path)
    return TestClient(app)


def test_pages_get_index_and_assets_are_served(tmp_path):
    client = make_app(tmp_path)
    for path in ("/", "/documents", "/documents/123/review", "/s/some-token"):
        response = client.get(path)
        assert response.status_code == 200 and "<title>app</title>" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert "default-src 'self'" in response.headers["content-security-policy"]
    assert client.get("/assets/app-1a2b.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"


def test_api_paths_never_fall_back_to_the_page(tmp_path):
    client = make_app(tmp_path)
    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/missing").status_code == 404
    assert client.get("/api").status_code == 404


def test_no_files_outside_the_web_folder(tmp_path):
    client = make_app(tmp_path)
    response = client.get("/..%2Fsecret.txt")
    assert "nope" not in response.text


def test_missing_build_means_api_only(tmp_path):
    app = FastAPI()
    mount_web(app, tmp_path / "missing")
    assert TestClient(app).get("/").status_code == 404
