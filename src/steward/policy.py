"""Policy gate: every planned action must pass every rule to be executable.

The gate is deliberately outside LLM control — in phase 2 the model proposes,
this layer disposes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from steward.executor import is_reversible
from steward.models import GateDecision, Plan

DEFAULT_PROTECTED_TAGS = {"env": "production"}


@dataclass(frozen=True)
class Policy:
    max_blast_radius: int = 3
    allow_irreversible: bool = False
    protected_tags: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PROTECTED_TAGS)
    )
    max_actions: int = 10
    max_monthly_change_usd: float = 500.0
    block_llm_proposed: bool = False  # --auto mode: LLM proposals need a human


def gate(plan: Plan, policy: Policy) -> list[GateDecision]:
    decisions: list[GateDecision] = []
    approved_count = 0
    approved_usd = 0.0
    for planned in plan.actions:
        reasons: list[str] = []
        resource = planned.finding.resource
        for key, value in policy.protected_tags.items():
            if resource.tags.get(key) == value:
                reasons.append(f"protected by tag {key}={value}")
        if planned.blast_radius > policy.max_blast_radius:
            reasons.append(
                f"blast radius {planned.blast_radius} exceeds policy max "
                f"{policy.max_blast_radius}"
            )
        if not policy.allow_irreversible and not is_reversible(planned.action.type):
            reasons.append(
                f"{planned.action.type.value} is irreversible and "
                "allow_irreversible is off"
            )
        if policy.block_llm_proposed and planned.finding.source == "llm":
            reasons.append(
                "llm-proposed action requires interactive approval (--auto blocks it)"
            )
        if approved_count >= policy.max_actions:
            reasons.append(f"max {policy.max_actions} actions per run reached")
        # float math: savings are 2dp-rounded, budgets coarse
        if approved_usd + planned.monthly_saving_usd > policy.max_monthly_change_usd:
            reasons.append(
                f"monthly-change budget ${policy.max_monthly_change_usd:.0f} "
                "would be exceeded"
            )
        allowed = not reasons
        if allowed:
            approved_count += 1
            approved_usd += planned.monthly_saving_usd
        decisions.append(
            GateDecision(action=planned, allowed=allowed, reasons=tuple(reasons))
        )
    return decisions
