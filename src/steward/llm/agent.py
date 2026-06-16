"""The investigation loop: Qwen explores the account through tools.

The loop is deliberately bounded: a tool-call cap and a token budget force a
finish even if the model never calls finish_investigation. LLM failures
degrade — investigate() never raises because of the model or the API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from steward.llm.client import LLMClient, LLMError
from steward.llm.tools import TOOL_SCHEMAS, ToolSession
from steward.models import Finding
from steward.providers.base import CloudProvider

SYSTEM_PROMPT = """\
You are Steward, an autonomous FinOps analyst reviewing one Alibaba Cloud account.

Your job: find cost waste that the deterministic detectors missed, and summarize
the situation for the operator.

Rules:
- Investigate with tools first. Look at resources, their metrics, and the
  existing findings before proposing anything.
- Propose an action ONLY with concrete evidence from tool results, via
  propose_action. Allowed action types: resize_ecs, release_eip, delete_disk,
  delete_snapshot, change_oss_class. Anything else is out of scope.
- Resources tagged env=production are protected by policy; do not propose
  actions on them.
- Be conservative: a wrong proposal costs operator trust.
- When you are done, call finish_investigation with a short plain-language
  summary (3-6 sentences) of the account's cost health and what you proposed.
"""

KICKOFF_PROMPT = (
    "Investigate this account for cost waste. The deterministic detectors have "
    "already run; review their findings, look for anything they missed, then "
    "finish with your summary."
)


@dataclass(frozen=True)
class AgentResult:
    findings: tuple[Finding, ...]
    narrative: str
    transcript: tuple[dict, ...]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    degraded: bool = False
    degraded_reason: str | None = None


def investigate(
    provider: CloudProvider,
    detector_findings: list[Finding],
    client: LLMClient,
    *,
    max_tool_calls: int = 20,
    max_total_tokens: int = 150_000,
    on_event: Callable[[dict], None] | None = None,
) -> AgentResult:
    session = ToolSession(provider, detector_findings)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": KICKOFF_PROMPT},
    ]
    transcript: list[dict] = []
    prompt_tokens = completion_tokens = 0
    tool_calls_used = 0
    narrative: str | None = None
    forced_finish_reason: str | None = None

    def emit(event: dict) -> None:
        transcript.append(event)
        if on_event is not None:
            on_event(event)

    while True:
        try:
            response = client.chat(messages, TOOL_SCHEMAS)
        except LLMError as exc:
            return AgentResult(
                findings=tuple(session.proposals),
                narrative=narrative
                or "(investigation aborted: LLM became unavailable)",
                transcript=tuple(transcript),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                degraded=True,
                degraded_reason=str(exc),
            )
        prompt_tokens += response.prompt_tokens
        completion_tokens += response.completion_tokens

        if not response.tool_calls:
            # The model is done talking; its content is the narrative.
            narrative = (response.content or "").strip() or None
            emit({"role": "assistant", "content": response.content})
            break

        emit(
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": c.id, "name": c.name, "arguments": c.arguments}
                    for c in response.tool_calls
                ],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": c.arguments},
                    }
                    for c in response.tool_calls
                ],
            }
        )
        # If the cap trips mid-batch, the assistant message above keeps all
        # tool_calls but only executed ones get a matching tool response. That
        # is a valid terminal state ONLY because we break out of the loop right
        # after and never call the API again — never resume from here.
        for call in response.tool_calls:
            if tool_calls_used >= max_tool_calls:
                forced_finish_reason = f"tool-call cap ({max_tool_calls}) reached"
                break
            result = session.dispatch(call)
            tool_calls_used += 1
            emit({"role": "tool", "name": call.name, "result": result})
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )
        if session.finished:
            narrative = session.summary
            break
        if forced_finish_reason:
            break
        if tool_calls_used >= max_tool_calls:
            forced_finish_reason = f"tool-call cap ({max_tool_calls}) reached"
            break
        if prompt_tokens + completion_tokens >= max_total_tokens:
            forced_finish_reason = f"token budget ({max_total_tokens}) reached"
            break

    if forced_finish_reason and not narrative:
        narrative = f"(investigation cut short: {forced_finish_reason})"

    return AgentResult(
        findings=tuple(session.proposals),
        narrative=narrative or "(no narrative provided)",
        transcript=tuple(transcript),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
