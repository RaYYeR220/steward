"""Domain models for Steward. Pure data, no behavior beyond derived totals."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class ResourceType(str, Enum):
    ECS_INSTANCE = "ecs_instance"
    EIP = "eip"
    DISK = "disk"
    SNAPSHOT = "snapshot"
    OSS_BUCKET = "oss_bucket"


class ActionType(str, Enum):
    RESIZE_ECS = "resize_ecs"
    RELEASE_EIP = "release_eip"
    DELETE_DISK = "delete_disk"
    DELETE_SNAPSHOT = "delete_snapshot"
    CHANGE_OSS_CLASS = "change_oss_class"


@dataclass(frozen=True)
class Resource:
    id: str
    type: ResourceType
    region: str
    name: str
    monthly_cost_usd: float
    # tags/spec are Mapping by contract: value objects are never mutated in place.
    tags: Mapping[str, str] = field(default_factory=dict)
    spec: Mapping[str, Any] = field(default_factory=dict)
    status: str = "running"  # running | stopped | available | in_use
    attached_to: str | None = None  # id of the resource this one is attached to
    age_days: int = 0
    cost_source: str = "exact"  # exact | billed | estimated | static (cost provenance)


@dataclass(frozen=True)
class Metrics:
    """Utilization over a lookback window. None = not applicable to this type."""

    resource_id: str
    window_days: int = 14
    avg_cpu_pct: float | None = None
    max_cpu_pct: float | None = None
    avg_mem_pct: float | None = None
    objects_total: int | None = None  # OSS
    objects_accessed_30d: int | None = None  # OSS


@dataclass(frozen=True)
class ActionSpec:
    type: ActionType
    resource_id: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    kind: str  # e.g. "ecs_overprovisioned"
    resource: Resource
    evidence: str  # one-line human-readable justification
    monthly_saving_usd: float
    action: ActionSpec
    source: Literal["detector", "llm"] = "detector"


@dataclass(frozen=True)
class PlannedAction:
    finding: Finding
    blast_radius: int  # 1 (trivially safe) .. 5 (dangerous)
    blast_reasons: tuple[str, ...] = ()

    @property
    def action(self) -> ActionSpec:
        return self.finding.action

    @property
    def monthly_saving_usd(self) -> float:
        return self.finding.monthly_saving_usd


@dataclass(frozen=True)
class Plan:
    actions: tuple[PlannedAction, ...]

    @property
    def total_monthly_saving_usd(self) -> float:
        return sum(a.monthly_saving_usd for a in self.actions)


@dataclass(frozen=True)
class GateDecision:
    action: PlannedAction
    allowed: bool
    reasons: tuple[str, ...] = ()


class ExecutionStatus(str, Enum):
    DRY_RUN = "dry_run"
    EXECUTED = "executed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ROLLBACK_FAILED = "rollback_failed"  # rollback itself failed; manual intervention
    BLOCKED = "blocked"
    NOT_REACHED = "not_reached"  # batch halted before this action


@dataclass(frozen=True)
class ExecutionRecord:
    action: PlannedAction
    status: ExecutionStatus
    reasons: tuple[str, ...] = ()
    before_state: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    records: tuple[ExecutionRecord, ...]

    @property
    def executed_saving_usd(self) -> float:
        return sum(
            r.action.monthly_saving_usd
            for r in self.records
            if r.status is ExecutionStatus.EXECUTED
        )
