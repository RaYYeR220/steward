import json

from steward.demo_seed import seed_demo
from steward.detectors import run_detectors
from steward.llm.agent import investigate
from steward.llm.client import ChatResponse, FakeLLM, LLMError, ToolCall


def setup_account():
    cloud = seed_demo()
    findings = run_detectors(cloud)
    return cloud, findings


def tc(name, args, call_id="c1"):
    return ToolCall(id=call_id, name=name, arguments=json.dumps(args))


PROPOSAL_ARGS = {
    "action_type": "release_eip",
    "resource_id": "eip-prod",
    "evidence": "EIP sits behind a load balancer",
    "estimated_monthly_saving_usd": 3.0,
}


def test_happy_path_proposal_and_finish():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[
            ChatResponse(
                tool_calls=(tc("list_resources", {}),),
                prompt_tokens=100,
                completion_tokens=20,
            ),
            ChatResponse(tool_calls=(tc("propose_action", PROPOSAL_ARGS, "c2"),)),
            ChatResponse(
                tool_calls=(
                    tc("finish_investigation", {"summary": "Found one extra saving."}, "c3"),
                )
            ),
        ]
    )
    result = investigate(cloud, findings, fake)
    assert len(result.findings) == 1
    assert result.findings[0].source == "llm"
    assert result.narrative == "Found one extra saving."
    assert result.degraded is False
    assert result.prompt_tokens == 100
    roles = [e["role"] for e in result.transcript]
    assert roles == ["assistant", "tool", "assistant", "tool", "assistant", "tool"]


def test_plain_content_response_becomes_narrative():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[ChatResponse(content="All tidy, nothing beyond the detectors.")]
    )
    result = investigate(cloud, findings, fake)
    assert result.narrative == "All tidy, nothing beyond the detectors."
    assert result.findings == ()


def test_malformed_arguments_are_fed_back_not_raised():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[
            ChatResponse(
                tool_calls=(ToolCall(id="c1", name="get_metrics", arguments="{broken"),)
            ),
            ChatResponse(
                tool_calls=(tc("finish_investigation", {"summary": "done"}, "c2"),)
            ),
        ]
    )
    result = investigate(cloud, findings, fake)
    error_events = [
        e
        for e in result.transcript
        if e["role"] == "tool" and "not valid JSON" in e["result"]
    ]
    assert len(error_events) == 1
    assert result.narrative == "done"


def test_tool_call_cap_forces_finish():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[
            ChatResponse(tool_calls=(tc("list_resources", {}, f"c{i}"),))
            for i in range(10)
        ]
    )
    result = investigate(cloud, findings, fake, max_tool_calls=3)
    assert "cut short" in result.narrative
    assert len([e for e in result.transcript if e["role"] == "tool"]) == 3


def test_token_budget_forces_finish():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[
            ChatResponse(
                tool_calls=(tc("list_resources", {}),),
                prompt_tokens=60_000,
                completion_tokens=1_000,
            ),
            ChatResponse(
                tool_calls=(tc("list_resources", {}, "c2"),),
                prompt_tokens=95_000,
                completion_tokens=1_000,
            ),
        ]
    )
    result = investigate(cloud, findings, fake, max_total_tokens=100_000)
    assert "token budget" in result.narrative


def test_llm_error_mid_loop_degrades_with_partial_results():
    cloud, findings = setup_account()

    class FailsAfterFirstCall:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ChatResponse(tool_calls=(tc("propose_action", PROPOSAL_ARGS),))
            raise LLMError("api down")

    result = investigate(cloud, findings, FailsAfterFirstCall())
    assert result.degraded is True
    assert "api down" in result.degraded_reason
    assert len(result.findings) == 1


def test_on_event_callback_sees_every_transcript_event():
    cloud, findings = setup_account()
    fake = FakeLLM(
        scripted=[
            ChatResponse(
                tool_calls=(tc("finish_investigation", {"summary": "ok"}),)
            )
        ]
    )
    seen = []
    result = investigate(cloud, findings, fake, on_event=seen.append)
    assert seen == list(result.transcript)


def test_single_response_with_many_calls_respects_tool_cap():
    cloud, findings = setup_account()
    many_calls = tuple(tc("list_resources", {}, f"c{i}") for i in range(10))
    fake = FakeLLM(scripted=[ChatResponse(tool_calls=many_calls)])
    result = investigate(cloud, findings, fake, max_tool_calls=3)
    tool_events = [e for e in result.transcript if e["role"] == "tool"]
    assert len(tool_events) == 3
    assert "cut short" in result.narrative
