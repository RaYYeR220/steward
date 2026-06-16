"""Detect ECS instances that are running far below their provisioned capacity."""
from __future__ import annotations

from steward.models import ActionSpec, ActionType, Finding, ResourceType
from steward.providers.base import CloudProvider

# One size down within the same family. Savings assume ~linear pricing per size.
DOWNSIZE: dict[str, str] = {
    "ecs.g7.4xlarge": "ecs.g7.2xlarge",
    "ecs.g7.2xlarge": "ecs.g7.xlarge",
    "ecs.g7.xlarge": "ecs.g7.large",
    "ecs.c7.4xlarge": "ecs.c7.2xlarge",
    "ecs.c7.2xlarge": "ecs.c7.xlarge",
    "ecs.c7.xlarge": "ecs.c7.large",
}

AVG_CPU_THRESHOLD = 10.0
MAX_CPU_THRESHOLD = 40.0
MIN_WINDOW_DAYS = 7
DOWNSIZE_SAVING_RATIO = 0.5  # one size down halves vCPU/RAM and ~halves the price


class EcsOverprovisionedDetector:
    kind = "ecs_overprovisioned"

    def detect(self, provider: CloudProvider) -> list[Finding]:
        findings: list[Finding] = []
        for res in provider.list_resources():
            if res.type is not ResourceType.ECS_INSTANCE or res.status != "running":
                continue
            target = DOWNSIZE.get(res.spec.get("instance_type", ""))
            if target is None:
                continue
            m = provider.get_metrics(res.id)
            if m is None or m.window_days < MIN_WINDOW_DAYS:
                continue
            if m.avg_cpu_pct is None or m.max_cpu_pct is None:
                continue
            if m.avg_cpu_pct >= AVG_CPU_THRESHOLD or m.max_cpu_pct >= MAX_CPU_THRESHOLD:
                continue
            saving = round(res.monthly_cost_usd * DOWNSIZE_SAVING_RATIO, 2)
            findings.append(
                Finding(
                    kind=self.kind,
                    resource=res,
                    evidence=(
                        f"avg CPU {m.avg_cpu_pct:.1f}%, max {m.max_cpu_pct:.1f}% "
                        f"over {m.window_days}d; downsize "
                        f"{res.spec['instance_type']} -> {target}"
                    ),
                    monthly_saving_usd=saving,
                    action=ActionSpec(
                        ActionType.RESIZE_ECS,
                        res.id,
                        {"target_instance_type": target},
                    ),
                )
            )
        return findings
