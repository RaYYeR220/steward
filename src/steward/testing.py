"""Shared factories for tests. In the package so all test modules can import them."""
from __future__ import annotations

from steward.models import (
    ActionSpec,
    ActionType,
    Finding,
    Metrics,
    PlannedAction,
    Resource,
    ResourceType,
)


def make_resource(
    id: str = "r-1",
    type: ResourceType = ResourceType.ECS_INSTANCE,
    *,
    region: str = "eu-central-1",
    name: str | None = None,
    monthly_cost_usd: float = 100.0,
    tags: dict[str, str] | None = None,
    spec: dict | None = None,
    status: str = "running",
    attached_to: str | None = None,
    age_days: int = 30,
    cost_source: str = "exact",
) -> Resource:
    return Resource(
        id=id,
        type=type,
        region=region,
        name=name or id,
        monthly_cost_usd=monthly_cost_usd,
        tags=tags or {},
        spec=spec or {},
        status=status,
        attached_to=attached_to,
        age_days=age_days,
        cost_source=cost_source,
    )


def make_metrics(resource_id: str = "r-1", **kwargs) -> Metrics:
    return Metrics(resource_id=resource_id, **kwargs)


def make_finding(
    resource: Resource,
    *,
    kind: str = "test_waste",
    saving: float = 10.0,
    action_type: ActionType = ActionType.DELETE_DISK,
    params: dict | None = None,
    source: str = "detector",
) -> Finding:
    return Finding(
        kind=kind,
        resource=resource,
        evidence="test evidence",
        monthly_saving_usd=saving,
        action=ActionSpec(action_type, resource.id, params or {}),
        source=source,
    )


def make_planned(finding: Finding, *, blast: int = 1) -> PlannedAction:
    return PlannedAction(finding=finding, blast_radius=blast, blast_reasons=("test",))
