"""Pydantic response models mirroring the snapshot contract (validate + OpenAPI)."""
from __future__ import annotations

from pydantic import BaseModel


class ResourceModel(BaseModel):
    id: str
    type: str
    name: str
    status: str
    region: str
    monthly_cost_usd: float
    cost_source: str
    tags: dict[str, str]
    age_days: int
    attached_to: str | None


class FindingModel(BaseModel):
    kind: str
    resource_id: str
    evidence: str
    monthly_saving_usd: float
    action_type: str
    source: str


class DecisionModel(BaseModel):
    resource_id: str
    action_type: str
    monthly_saving_usd: float
    blast_radius: int
    blast_reasons: list[str]
    allowed: bool
    reasons: list[str]
    source: str


class RecordModel(BaseModel):
    resource_id: str
    action_type: str
    status: str
    monthly_saving_usd: float
    error: str | None


class ScanResponse(BaseModel):
    resources: list[ResourceModel]
    findings: list[FindingModel]
    total_monthly_usd: float
    potential_saving_usd: float
    warnings: list[str]


class PlanResponse(BaseModel):
    decisions: list[DecisionModel]
    allowed_saving_usd: float
    blocked_saving_usd: float


class AgentResponse(BaseModel):
    narrative: str
    findings: list[FindingModel]
    decisions: list[DecisionModel]
    allowed_saving_usd: float
    blocked_saving_usd: float
    prompt_tokens: int
    completion_tokens: int
    degraded: bool
    degraded_reason: str | None
    transcript: list[dict]
