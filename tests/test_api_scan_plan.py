from fastapi.testclient import TestClient

from steward.api.app import create_app


def client(**env):
    return TestClient(create_app())


def test_health():
    assert client().get("/api/health").json() == {"status": "ok"}


def test_scan_mock_contract():
    r = client().get("/api/scan?provider=mock")
    assert r.status_code == 200
    body = r.json()
    assert body["total_monthly_usd"] == 1278.0
    assert body["potential_saving_usd"] == 561.5
    assert len(body["resources"]) == 11
    assert all({"id", "type", "monthly_cost_usd", "cost_source"} <= set(res) for res in body["resources"])


def test_plan_mock_gate_decisions():
    r = client().get("/api/plan?provider=mock&max_blast=4&allow_irreversible=true")
    assert r.status_code == 200
    body = r.json()
    assert body["allowed_saving_usd"] == 421.5
    blocked = [d for d in body["decisions"] if not d["allowed"]]
    assert any(d["resource_id"] == "i-prod-batch" for d in blocked)


def test_provider_not_in_allowlist_is_forbidden(monkeypatch):
    monkeypatch.setenv("STEWARD_API_PROVIDERS", "mock")
    r = TestClient(create_app()).get("/api/scan?provider=alibaba")
    assert r.status_code == 403
    assert "not allowed" in r.json()["error"]


def test_unknown_provider_is_400():
    r = client().get("/api/scan?provider=gcp")
    assert r.status_code == 400
