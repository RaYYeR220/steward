"""Turn findings into an ordered plan with deterministic blast-radius scores.

Blast radius 1-5: how much can go wrong if this action misbehaves.
Phase 2 will let Qwen adjust scores with reasoning; the deterministic floor stays.
"""
from __future__ import annotations

from steward.models import ActionType, Finding, Plan, PlannedAction
from steward.providers.base import CloudProvider

# NOTE: base 3 for RESIZE_ECS plus the "+1 if running" modifier means resizing
# a RUNNING instance always scores 4 — above the default Policy cap of 3. That
# is deliberate: the agent never restarts live compute without an explicit
# --max-blast 4 opt-in from the operator.
BASE_BLAST: dict[ActionType, int] = {
    ActionType.DELETE_SNAPSHOT: 1,
    ActionType.RELEASE_EIP: 1,
    ActionType.DELETE_DISK: 2,
    ActionType.CHANGE_OSS_CLASS: 2,
    ActionType.RESIZE_ECS: 3,  # requires an instance restart
}


def score_blast(
    finding: Finding, provider: CloudProvider
) -> tuple[int, tuple[str, ...]]:
    action_type = finding.action.type
    score = BASE_BLAST[action_type]
    reasons = [f"base risk for {action_type.value}: {score}"]
    dependents = [
        r for r in provider.list_resources() if r.attached_to == finding.resource.id
    ]
    if dependents:
        score += 1
        names = ", ".join(d.id for d in dependents)
        reasons.append(f"{len(dependents)} dependent resource(s): {names}")
    if finding.resource.status == "running":
        score += 1
        reasons.append("resource is currently running (action causes interruption)")
    if finding.source == "llm":
        score += 1
        reasons.append("proposed by LLM without deterministic evidence")
    return min(score, 5), tuple(reasons)


def build_plan(findings: list[Finding], provider: CloudProvider) -> Plan:
    planned = [
        PlannedAction(finding=f, blast_radius=score, blast_reasons=reasons)
        for f in findings
        for score, reasons in (score_blast(f, provider),)
    ]
    # Safe-first ordering: lowest blast radius first; among equals, biggest saving.
    planned.sort(key=lambda a: (a.blast_radius, -a.monthly_saving_usd))
    return Plan(actions=tuple(planned))
