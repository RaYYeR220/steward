"""Detect elastic IPs that bill while serving no running instance."""
from __future__ import annotations

from steward.models import ActionSpec, ActionType, Finding, ResourceType
from steward.providers.base import CloudProvider


class IdleEipDetector:
    kind = "idle_eip"

    def detect(self, provider: CloudProvider) -> list[Finding]:
        findings: list[Finding] = []
        for res in provider.list_resources():
            if res.type is not ResourceType.EIP:
                continue
            if res.attached_to:
                attached = provider.get_resource(res.attached_to)
                if attached is not None and attached.status == "running":
                    continue
                if attached is None:
                    evidence = (
                        f"attached to {res.attached_to!r}, which no longer exists"
                    )
                else:
                    evidence = f"attached to stopped instance {attached.id}"
            else:
                evidence = "not attached to any instance"
            findings.append(
                Finding(
                    kind=self.kind,
                    resource=res,
                    evidence=f"{evidence}; idle EIPs still bill hourly",
                    monthly_saving_usd=res.monthly_cost_usd,
                    action=ActionSpec(ActionType.RELEASE_EIP, res.id),
                )
            )
        return findings
