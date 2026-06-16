"""Live integration test against the real Qwen Cloud API.

Skipped by default — set QWEN_LIVE=1 to run (burns real tokens, ~$0.01).
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("QWEN_LIVE"),
    reason="live Qwen test: set QWEN_LIVE=1 to run (burns real tokens)",
)


def test_live_investigation_makes_tool_calls_and_finishes():
    from steward.config import load_qwen_settings
    from steward.demo_seed import seed_demo
    from steward.detectors import run_detectors
    from steward.llm.agent import investigate
    from steward.llm.client import QwenClient

    client = QwenClient(load_qwen_settings())
    cloud = seed_demo()
    findings = run_detectors(cloud)
    result = investigate(cloud, findings, client, max_tool_calls=15)
    assert result.degraded is False, result.degraded_reason
    tool_events = [e for e in result.transcript if e["role"] == "tool"]
    assert len(tool_events) >= 1
    assert result.narrative
    # every accepted proposal must be a valid llm-sourced finding
    for finding in result.findings:
        assert finding.source == "llm"
        assert finding.monthly_saving_usd >= 0
