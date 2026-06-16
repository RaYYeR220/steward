"""Detect OSS buckets paying Standard-tier prices for rarely accessed objects."""
from __future__ import annotations

from steward.models import ActionSpec, ActionType, Finding, ResourceType
from steward.providers.base import CloudProvider

ACCESS_RATIO_THRESHOLD = 0.05  # <5% of objects touched in 30 days = cold
IA_SAVING_RATIO = 0.45  # IA storage is ~45% cheaper than Standard


class OssColdBucketDetector:
    kind = "oss_cold_bucket"

    def detect(self, provider: CloudProvider) -> list[Finding]:
        findings: list[Finding] = []
        for res in provider.list_resources():
            if res.type is not ResourceType.OSS_BUCKET:
                continue
            if res.spec.get("storage_class") != "Standard":
                continue
            m = provider.get_metrics(res.id)
            if m is None or not m.objects_total:
                continue
            if m.objects_accessed_30d is None:
                # Access recency is unavailable (e.g. the live OSS adapter can't
                # cheaply get per-object recency). Do NOT fabricate "0 accessed"
                # — skip and let the Qwen agent propose the change from the
                # visible storage-class + age signal instead.
                continue
            accessed = m.objects_accessed_30d
            ratio = accessed / m.objects_total
            if ratio >= ACCESS_RATIO_THRESHOLD:
                continue
            saving = round(res.monthly_cost_usd * IA_SAVING_RATIO, 2)
            findings.append(
                Finding(
                    kind=self.kind,
                    resource=res,
                    evidence=(
                        f"{accessed}/{m.objects_total} objects accessed in 30d "
                        f"({ratio:.1%}); move Standard -> IA"
                    ),
                    monthly_saving_usd=saving,
                    action=ActionSpec(
                        ActionType.CHANGE_OSS_CLASS,
                        res.id,
                        {"target_storage_class": "IA"},
                    ),
                )
            )
        return findings
