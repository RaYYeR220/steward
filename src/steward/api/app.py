"""FastAPI app exposing the engine read-only / dry-run. Real mutations stay in the CLI.

Safety invariants:
- the API never sets allow_destructive and never executes (dry-run only);
- providers are gated by the STEWARD_API_PROVIDERS allowlist;
- a missing cloud/LLM key degrades gracefully, never a traceback.
"""
from __future__ import annotations

import json
import os
import queue
import threading

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from steward.api.models import AgentResponse, PlanResponse, ScanResponse
from steward.config import load_qwen_settings
from steward.demo_seed import seed_demo
from steward.detectors import run_detectors
from steward.llm.agent import AgentResult, investigate
from steward.llm.client import LLMError, QwenClient
from steward.planner import build_plan
from steward.policy import Policy, gate
from steward.providers.base import CloudError
from steward.snapshot import decisions_snapshot, finding_dict, plan_snapshot, scan_snapshot


def _allowed_providers() -> set[str]:
    raw = os.environ.get("STEWARD_API_PROVIDERS", "mock,alibaba")
    return {p.strip() for p in raw.split(",") if p.strip()}


_KNOWN_PROVIDERS = {"mock", "alibaba"}


def _make_provider(name: str):
    if name not in _KNOWN_PROVIDERS:
        raise ValueError(f"unknown provider: {name!r}")
    if name not in _allowed_providers():
        raise PermissionError(f"provider {name!r} is not allowed")
    if name == "mock":
        return seed_demo()
    if name == "alibaba":
        from steward.providers.alibaba.config import load_alibaba_config
        from steward.providers.alibaba.provider import AlibabaCloudProvider

        # read-only: never pass allow_destructive from the API
        return AlibabaCloudProvider(load_alibaba_config())


class AgentRequest(BaseModel):
    provider: str = "mock"
    auto: bool = False
    max_blast: int = 3
    allow_irreversible: bool = False


def _make_llm_client():
    settings = load_qwen_settings()
    if not settings.api_key:
        return None, "QWEN_API_KEY is not configured"
    try:
        return QwenClient(settings), None
    except LLMError as exc:
        return None, str(exc)


def create_app() -> FastAPI:
    app = FastAPI(title="Steward API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PermissionError)
    async def _forbidden(_: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    @app.exception_handler(ValueError)
    async def _bad_request(_: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(CloudError)
    async def _cloud_error(_: Request, exc: CloudError):
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/scan", response_model=ScanResponse)
    def scan(provider: str = Query("mock")):
        return scan_snapshot(_make_provider(provider))

    @app.get("/api/plan", response_model=PlanResponse)
    def plan(
        provider: str = Query("mock"),
        max_blast: int = Query(3),
        allow_irreversible: bool = Query(False),
    ):
        policy = Policy(max_blast_radius=max_blast, allow_irreversible=allow_irreversible)
        return plan_snapshot(_make_provider(provider), policy)

    @app.post("/api/agent", response_model=AgentResponse)
    def agent(req: AgentRequest):
        provider = _make_provider(req.provider)
        detector_findings = run_detectors(provider)
        client, problem = _make_llm_client()
        if client is None:
            agent_result = AgentResult(
                findings=(),
                narrative="(LLM unavailable - detector-only run)",
                transcript=(),
                degraded=True,
                degraded_reason=problem,
            )
        else:
            agent_result = investigate(provider, detector_findings, client)
        findings = detector_findings + list(agent_result.findings)
        plan = build_plan(findings, provider)
        policy = Policy(
            max_blast_radius=req.max_blast,
            allow_irreversible=req.allow_irreversible,
            block_llm_proposed=req.auto,
        )
        decisions = gate(plan, policy)
        snap = decisions_snapshot(decisions)
        return {
            "narrative": agent_result.narrative,
            "findings": [finding_dict(f) for f in findings],
            "decisions": snap["decisions"],
            "allowed_saving_usd": snap["allowed_saving_usd"],
            "blocked_saving_usd": snap["blocked_saving_usd"],
            "prompt_tokens": agent_result.prompt_tokens,
            "completion_tokens": agent_result.completion_tokens,
            "degraded": agent_result.degraded,
            "degraded_reason": agent_result.degraded_reason,
            "transcript": list(agent_result.transcript),
        }

    @app.get("/api/agent/stream")
    def agent_stream(
        provider: str = Query("mock"),
        max_blast: int = Query(3),
        allow_irreversible: bool = Query(False),
    ):
        prov = _make_provider(provider)
        detector_findings = run_detectors(prov)
        client, problem = _make_llm_client()
        # Note: no mid-stream client-disconnect cancellation — investigations are
        # short and the worker is a daemon thread, so this is fine for the demo.
        events: "queue.Queue[dict | None]" = queue.Queue()

        def classify(event: dict) -> str:
            if event.get("role") == "assistant" and "tool_calls" in event:
                return "tool_call"
            if event.get("role") == "tool" and '"accepted": true' in (event.get("result") or ""):
                return "proposal"
            if event.get("role") == "assistant":
                return "narrative"
            return "tool_result"

        def sse(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload)}\n\n"

        def worker():
            try:
                if client is None:
                    result = AgentResult(
                        findings=(), narrative="(LLM unavailable - detector-only run)",
                        transcript=(), degraded=True, degraded_reason=problem,
                    )
                else:
                    result = investigate(
                        prov, detector_findings, client,
                        on_event=lambda e: events.put(e),
                    )
                findings = detector_findings + list(result.findings)
                plan = build_plan(findings, prov)
                policy = Policy(
                    max_blast_radius=max_blast, allow_irreversible=allow_irreversible
                )
                snap = decisions_snapshot(gate(plan, policy))
                events.put({
                    "__done__": True,
                    "narrative": result.narrative,
                    "degraded": result.degraded,
                    "degraded_reason": result.degraded_reason,
                    "findings": [finding_dict(f) for f in findings],
                    "decisions": snap["decisions"],
                    "allowed_saving_usd": snap["allowed_saving_usd"],
                    "blocked_saving_usd": snap["blocked_saving_usd"],
                })
            except Exception as exc:  # worker boundary: never leave the stream hanging
                events.put({"__error__": True, "error": str(exc)})
            finally:
                events.put(None)

        def generate():
            threading.Thread(target=worker, daemon=True).start()
            while True:
                event = events.get()
                if event is None:
                    break
                if event.get("__done__"):
                    yield sse("done", {k: v for k, v in event.items() if k != "__done__"})
                elif event.get("__error__"):
                    yield sse("error", {"error": event["error"]})
                else:
                    yield sse(classify(event), event)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


app = create_app()
