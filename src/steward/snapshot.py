"""Serialize engine state into plain JSON-able dicts — the single dashboard contract.

Pure functions, no FastAPI dependency. Numbers match what the CLI prints so the
dashboard and CLI never disagree.
"""
from __future__ import annotations

from steward.detectors import run_detectors
from steward.executor import run as execute_run
from steward.models import (
    ExecutionRecord,
    Finding,
    GateDecision,
    Resource,
    RunResult,
)
from steward.planner import build_plan
from steward.policy import Policy, gate


def resource_dict(res: Resource) -> dict:
    return {
        "id": res.id,
        "type": res.type.value,
        "name": res.name,
        "status": res.status,
        "region": res.region,
        "monthly_cost_usd": res.monthly_cost_usd,
        "cost_source": res.cost_source,
        "tags": dict(res.tags),
        "age_days": res.age_days,
        "attached_to": res.attached_to,
    }


def finding_dict(f: Finding) -> dict:
    return {
        "kind": f.kind,
        "resource_id": f.resource.id,
        "evidence": f.evidence,
        "monthly_saving_usd": f.monthly_saving_usd,
        "action_type": f.action.type.value,
        "source": f.source,
    }


def decision_dict(d: GateDecision) -> dict:
    planned = d.action
    return {
        "resource_id": planned.finding.resource.id,
        "action_type": planned.action.type.value,
        "monthly_saving_usd": planned.monthly_saving_usd,
        "blast_radius": planned.blast_radius,
        "blast_reasons": list(planned.blast_reasons),
        "allowed": d.allowed,
        "reasons": list(d.reasons),
        "source": planned.finding.source,
    }


def record_dict(r: ExecutionRecord) -> dict:
    return {
        "resource_id": r.action.finding.resource.id,
        "action_type": r.action.action.type.value,
        "status": r.status.value,
        "monthly_saving_usd": r.action.monthly_saving_usd,
        "error": r.error,
    }


def scan_snapshot(provider) -> dict:
    resources = provider.list_resources()
    findings = run_detectors(provider)
    return {
        "resources": [resource_dict(r) for r in resources],
        "findings": [finding_dict(f) for f in findings],
        "total_monthly_usd": round(sum(r.monthly_cost_usd for r in resources), 2),
        "potential_saving_usd": round(sum(f.monthly_saving_usd for f in findings), 2),
        "warnings": list(getattr(provider, "last_warnings", [])),
    }


def decisions_snapshot(decisions: list[GateDecision]) -> dict:
    return {
        "decisions": [decision_dict(d) for d in decisions],
        "allowed_saving_usd": round(
            sum(d.action.monthly_saving_usd for d in decisions if d.allowed), 2
        ),
        "blocked_saving_usd": round(
            sum(d.action.monthly_saving_usd for d in decisions if not d.allowed), 2
        ),
    }


def plan_snapshot(provider, policy: Policy) -> dict:
    findings = run_detectors(provider)
    plan = build_plan(findings, provider)
    return decisions_snapshot(gate(plan, policy))


def run_snapshot(
    result: RunResult,
    *,
    dry_run: bool,
    total_monthly_usd: float,
    narrative: str | None = None,
) -> dict:
    applied = round(result.executed_saving_usd, 2)
    return {
        "records": [record_dict(r) for r in result.records],
        "applied_saving_usd": applied,
        "before_usd": round(total_monthly_usd, 2),
        "after_usd": round(total_monthly_usd - applied, 2),
        "mode": "dry_run" if dry_run else "execute",
        "narrative": narrative,
    }
