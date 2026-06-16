"""Detect billed-but-useless block storage: unattached disks, orphaned snapshots."""
from __future__ import annotations

from steward.models import ActionSpec, ActionType, Finding, ResourceType
from steward.providers.base import CloudProvider

MIN_DISK_AGE_DAYS = 14  # don't flag disks someone detached five minutes ago
MIN_SNAPSHOT_AGE_DAYS = 180


class UnattachedDiskDetector:
    kind = "unattached_disk"

    def detect(self, provider: CloudProvider) -> list[Finding]:
        findings: list[Finding] = []
        for res in provider.list_resources():
            if res.type is not ResourceType.DISK or res.attached_to is not None:
                continue
            if res.age_days < MIN_DISK_AGE_DAYS:
                continue
            findings.append(
                Finding(
                    kind=self.kind,
                    resource=res,
                    evidence=(
                        f"not attached to any instance (created {res.age_days}d ago); "
                        "deletion is snapshot-protected"
                    ),
                    monthly_saving_usd=res.monthly_cost_usd,
                    action=ActionSpec(ActionType.DELETE_DISK, res.id),
                )
            )
        return findings


class OldSnapshotDetector:
    kind = "old_snapshot"

    def detect(self, provider: CloudProvider) -> list[Finding]:
        findings: list[Finding] = []
        for res in provider.list_resources():
            if res.type is not ResourceType.SNAPSHOT:
                continue
            if res.age_days < MIN_SNAPSHOT_AGE_DAYS:
                continue
            source = res.spec.get("source_disk")
            if source is None:
                continue  # unknown provenance — keep (phase-1 conservatism)
            if provider.get_resource(source) is not None:
                continue  # source disk still exists — keep
            findings.append(
                Finding(
                    kind=self.kind,
                    resource=res,
                    evidence=f"{res.age_days}d old and its source disk no longer exists",
                    monthly_saving_usd=res.monthly_cost_usd,
                    action=ActionSpec(ActionType.DELETE_SNAPSHOT, res.id),
                )
            )
        return findings
