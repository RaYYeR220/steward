"""Agent tool schemas and the stateful dispatcher over engine primitives.

Every result returned to the model is a JSON string. Validation failures are
structured errors fed back to the model — they never raise.
"""
from __future__ import annotations

import json
import math

from steward.llm.client import ToolCall
from steward.models import ActionSpec, ActionType, Finding, Resource
from steward.providers.base import CloudProvider

REQUIRED_PARAMS: dict[ActionType, tuple[str, ...]] = {
    ActionType.RESIZE_ECS: ("target_instance_type",),
    ActionType.RELEASE_EIP: (),
    ActionType.DELETE_DISK: (),
    ActionType.DELETE_SNAPSHOT: (),
    ActionType.CHANGE_OSS_CLASS: ("target_storage_class",),
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_resources",
            "description": "List every resource in the account with status, cost, tags and attachments.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrics",
            "description": "Utilization metrics for one resource (CPU for instances, object access for OSS buckets).",
            "parameters": {
                "type": "object",
                "properties": {"resource_id": {"type": "string"}},
                "required": ["resource_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_findings",
            "description": "Waste findings already produced by Steward's deterministic detectors.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_action",
            "description": (
                "Propose one cost-saving action you found beyond the deterministic "
                "findings. Cite concrete evidence from tool results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": [t.value for t in ActionType],
                    },
                    "resource_id": {"type": "string"},
                    "params": {"type": "object"},
                    "evidence": {"type": "string"},
                    "estimated_monthly_saving_usd": {"type": "number"},
                },
                "required": [
                    "action_type",
                    "resource_id",
                    "evidence",
                    "estimated_monthly_saving_usd",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_investigation",
            "description": "Call when done. Provide a short narrative summary of what you found.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


def _resource_dict(res: Resource) -> dict:
    return {
        "id": res.id,
        "type": res.type.value,
        "region": res.region,
        "name": res.name,
        "status": res.status,
        "monthly_cost_usd": res.monthly_cost_usd,
        "tags": dict(res.tags),
        "spec": dict(res.spec),
        "attached_to": res.attached_to,
        "age_days": res.age_days,
    }


class ToolSession:
    """One investigation's tool state: accepted proposals and the finish signal."""

    def __init__(
        self, provider: CloudProvider, detector_findings: list[Finding]
    ) -> None:
        self._provider = provider
        self._detector_findings = list(detector_findings)
        self.proposals: list[Finding] = []
        self.finished = False
        self.summary: str | None = None

    # -- dispatch ---------------------------------------------------------

    def dispatch(self, call: ToolCall) -> str:
        try:
            args = json.loads(call.arguments) if call.arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"arguments are not valid JSON: {exc}"})
        if not isinstance(args, dict):
            return json.dumps({"error": "arguments must be a JSON object"})
        handler = getattr(self, f"_tool_{call.name}", None)
        if handler is None:
            return json.dumps({"error": f"unknown tool: {call.name}"})
        return handler(args)

    # -- read tools --------------------------------------------------------

    def _tool_list_resources(self, args: dict) -> str:
        resources = [_resource_dict(r) for r in self._provider.list_resources()]
        return json.dumps({"resources": resources})

    def _tool_get_metrics(self, args: dict) -> str:
        resource_id = args.get("resource_id")
        if not resource_id:
            return json.dumps({"error": "resource_id is required"})
        metrics = self._provider.get_metrics(resource_id)
        if metrics is None:
            return json.dumps({"metrics": None})
        return json.dumps(
            {
                "metrics": {
                    "window_days": metrics.window_days,
                    "avg_cpu_pct": metrics.avg_cpu_pct,
                    "max_cpu_pct": metrics.max_cpu_pct,
                    "avg_mem_pct": metrics.avg_mem_pct,
                    "objects_total": metrics.objects_total,
                    "objects_accessed_30d": metrics.objects_accessed_30d,
                }
            }
        )

    def _tool_get_findings(self, args: dict) -> str:
        findings = [
            {
                "kind": f.kind,
                "resource_id": f.resource.id,
                "evidence": f.evidence,
                "monthly_saving_usd": f.monthly_saving_usd,
                "action_type": f.action.type.value,
                "params": dict(f.action.params),
            }
            for f in self._detector_findings
        ]
        return json.dumps({"findings": findings})

    # -- write tools ---------------------------------------------------------

    def _tool_propose_action(self, args: dict) -> str:
        error = self._validate_proposal(args)
        if error:
            return json.dumps({"accepted": False, "error": error})
        action_type = ActionType(args["action_type"])
        resource = self._provider.get_resource(args["resource_id"])
        saving = min(
            float(args["estimated_monthly_saving_usd"]), resource.monthly_cost_usd
        )
        finding = Finding(
            kind=f"llm_{action_type.value}",
            resource=resource,
            evidence=args["evidence"].strip(),
            monthly_saving_usd=round(saving, 2),
            action=ActionSpec(action_type, resource.id, dict(args.get("params") or {})),
            source="llm",
        )
        self.proposals.append(finding)
        return json.dumps({"accepted": True})

    def _validate_proposal(self, args: dict) -> str | None:
        try:
            action_type = ActionType(args.get("action_type"))
        except ValueError:
            allowed = ", ".join(t.value for t in ActionType)
            return f"unknown action_type; allowed: {allowed}"
        resource = self._provider.get_resource(args.get("resource_id") or "")
        if resource is None:
            return f"no such resource: {args.get('resource_id')!r}"
        params = args.get("params") or {}
        if not isinstance(params, dict):
            return "params must be an object"
        for required in REQUIRED_PARAMS[action_type]:
            if required not in params:
                return f"missing required param {required!r} for {action_type.value}"
        if action_type is ActionType.RESIZE_ECS and params.get(
            "target_instance_type"
        ) == resource.spec.get("instance_type"):
            return "target_instance_type equals the current instance type"
        try:
            saving = float(args.get("estimated_monthly_saving_usd"))
        except (TypeError, ValueError):
            return "estimated_monthly_saving_usd must be a number"
        if not math.isfinite(saving):
            return "estimated_monthly_saving_usd must be a finite number"
        if saving < 0:
            return "estimated_monthly_saving_usd must be non-negative"
        evidence = args.get("evidence")
        if not isinstance(evidence, str) or not evidence.strip():
            return "evidence must be a non-empty string"
        duplicate = any(
            f.action.type is action_type and f.resource.id == resource.id
            for f in self._detector_findings + self.proposals
        )
        if duplicate:
            return "duplicate: an equivalent finding already exists"
        return None

    def _tool_finish_investigation(self, args: dict) -> str:
        self.finished = True
        self.summary = str(args.get("summary") or "").strip() or None
        return json.dumps({"ok": True})
