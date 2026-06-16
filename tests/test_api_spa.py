"""The optional same-origin SPA mount (STEWARD_SPA_DIR) used by the FC deploy."""
from fastapi.testclient import TestClient

from steward.api.app import create_app


def test_no_spa_mount_by_default():
    # without STEWARD_SPA_DIR there is no "/" route — only the API exists.
    r = TestClient(create_app()).get("/")
    assert r.status_code == 404


def test_spa_served_when_dir_set(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>steward-spa</title>", encoding="utf-8"
    )
    monkeypatch.setenv("STEWARD_SPA_DIR", str(tmp_path))
    c = TestClient(create_app())

    root = c.get("/")
    assert root.status_code == 200
    assert "steward-spa" in root.text
    assert "text/html" in root.headers["content-type"]

    # the /api/* routes still take precedence over the catch-all static mount
    assert c.get("/api/health").json() == {"status": "ok"}
