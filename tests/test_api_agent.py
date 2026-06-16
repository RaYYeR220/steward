from fastapi.testclient import TestClient

from steward.api import app as app_module
from steward.api.app import create_app
from steward.llm.agent import AgentResult
from steward.models import ActionSpec, ActionType, Finding


def fake_investigate(provider, detector_findings, client, **kwargs):
    eip = provider.get_resource("eip-orphan")
    finding = Finding(
        kind="llm_release_eip",
        resource=eip,
        evidence="llm found this",
        monthly_saving_usd=9.0,
        action=ActionSpec(ActionType.RELEASE_EIP, "eip-orphan"),
        source="llm",
    )
    return AgentResult(
        findings=(finding,),
        narrative="One extra saving.",
        transcript=({"role": "assistant", "content": "done"},),
        prompt_tokens=10,
        completion_tokens=5,
    )


def patched_client(monkeypatch):
    monkeypatch.setattr(app_module, "_make_llm_client", lambda: (object(), None))
    monkeypatch.setattr(app_module, "investigate", fake_investigate)
    return TestClient(create_app())


def test_agent_returns_narrative_and_plan(monkeypatch):
    c = patched_client(monkeypatch)
    r = c.post("/api/agent", json={"provider": "mock", "auto": False, "max_blast": 4, "allow_irreversible": True})
    assert r.status_code == 200
    body = r.json()
    assert body["narrative"] == "One extra saving."
    assert body["degraded"] is False
    # the llm finding is present among the decisions
    assert any(d["source"] == "llm" for d in body["decisions"])


def test_agent_auto_blocks_llm_decisions(monkeypatch):
    c = patched_client(monkeypatch)
    r = c.post("/api/agent", json={"provider": "mock", "auto": True, "max_blast": 4, "allow_irreversible": True})
    body = r.json()
    llm = next(d for d in body["decisions"] if d["source"] == "llm")
    assert llm["allowed"] is False
    assert any("interactive approval" in reason for reason in llm["reasons"])


def test_agent_degrades_without_llm_key(monkeypatch):
    monkeypatch.setattr(app_module, "_make_llm_client", lambda: (None, "QWEN_API_KEY is not configured"))
    c = TestClient(create_app())
    r = c.post("/api/agent", json={"provider": "mock", "auto": True})
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True
    assert "QWEN_API_KEY" in body["degraded_reason"]
