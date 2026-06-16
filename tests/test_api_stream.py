from fastapi.testclient import TestClient

from steward.api import app as app_module
from steward.api.app import create_app
from steward.llm.agent import AgentResult


def fake_investigate_with_events(provider, detector_findings, client, *, on_event=None, **kwargs):
    events = [
        {"role": "assistant", "tool_calls": [{"id": "1", "name": "list_resources", "arguments": "{}"}]},
        {"role": "tool", "name": "list_resources", "result": "{\"resources\": []}"},
        {"role": "assistant", "content": "summary"},
    ]
    for e in events:
        if on_event:
            on_event(e)
    return AgentResult(findings=(), narrative="summary", transcript=tuple(events))


def stream_client(monkeypatch):
    monkeypatch.setattr(app_module, "_make_llm_client", lambda: (object(), None))
    monkeypatch.setattr(app_module, "investigate", fake_investigate_with_events)
    return TestClient(create_app())


def test_stream_emits_events_then_done(monkeypatch):
    c = stream_client(monkeypatch)
    with c.stream("GET", "/api/agent/stream?provider=mock") as r:
        assert r.status_code == 200
        text = "".join(chunk for chunk in r.iter_text())
    assert "event: tool_call" in text
    assert "event: done" in text
    assert "summary" in text  # narrative in the done payload


def test_stream_degrades_without_key(monkeypatch):
    monkeypatch.setattr(app_module, "_make_llm_client", lambda: (None, "QWEN_API_KEY is not configured"))
    c = TestClient(create_app())
    with c.stream("GET", "/api/agent/stream?provider=mock") as r:
        text = "".join(chunk for chunk in r.iter_text())
    assert "event: done" in text
    assert "degraded" in text


def test_stream_emits_error_event_when_worker_raises(monkeypatch):
    def boom(provider, detector_findings, client, *, on_event=None, **kwargs):
        raise RuntimeError("kaboom in worker")

    monkeypatch.setattr(app_module, "_make_llm_client", lambda: (object(), None))
    monkeypatch.setattr(app_module, "investigate", boom)
    c = TestClient(create_app())
    with c.stream("GET", "/api/agent/stream?provider=mock") as r:
        text = "".join(chunk for chunk in r.iter_text())
    assert "event: error" in text
    assert "kaboom" in text
