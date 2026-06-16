"""Waste detectors. Each detector scans the provider and returns Findings."""
from __future__ import annotations

from steward.detectors.ecs import EcsOverprovisionedDetector
from steward.detectors.eip import IdleEipDetector
from steward.detectors.oss import OssColdBucketDetector
from steward.detectors.storage import OldSnapshotDetector, UnattachedDiskDetector
from steward.models import Finding
from steward.providers.base import CloudProvider


# Detectors share a structural interface: .kind plus .detect(provider) -> list[Finding].
def all_detectors() -> list:
    return [
        EcsOverprovisionedDetector(),
        IdleEipDetector(),
        UnattachedDiskDetector(),
        OldSnapshotDetector(),
        OssColdBucketDetector(),
    ]


def run_detectors(provider: CloudProvider) -> list[Finding]:
    findings: list[Finding] = []
    for detector in all_detectors():
        findings.extend(detector.detect(provider))
    return findings
