"""A deliberately wasteful demo account for tests, the CLI mock provider, and the demo video.

Planted waste (expected detector output):
- i-staging-app   ecs_overprovisioned  saving $280.00 (560 * 0.5)
- i-prod-batch    ecs_overprovisioned  saving $140.00 (280 * 0.5) — gate blocks it (env=production)
- eip-orphan      idle_eip             saving $9.00
- d-orphan-1      unattached_disk      saving $44.00
- d-orphan-2      unattached_disk      saving $18.00
- snap-old-1/2    old_snapshot         saving $6.00 each
- oss-archives    oss_cold_bucket      saving $58.50 (130 * 0.45)
Total potential: $561.50/mo.
"""
from __future__ import annotations

from steward.models import Metrics, Resource, ResourceType
from steward.providers.mock import MockCloud

_REGION = "eu-central-1"


def seed_demo() -> MockCloud:
    cloud = MockCloud()

    # --- healthy resources that must never be flagged ----------------------
    cloud.add(
        Resource(
            id="i-prod-web",
            type=ResourceType.ECS_INSTANCE,
            region=_REGION,
            name="prod-web",
            monthly_cost_usd=210.0,
            tags={"env": "production"},
            spec={"instance_type": "ecs.g7.xlarge"},
            status="running",
            age_days=400,
        ),
        Metrics(resource_id="i-prod-web", avg_cpu_pct=55.0, max_cpu_pct=92.0),
    )
    cloud.add(
        Resource(
            id="d-prod-web-root",
            type=ResourceType.DISK,
            region=_REGION,
            name="prod-web-root",
            monthly_cost_usd=12.0,
            spec={"size_gb": 120},
            status="in_use",
            attached_to="i-prod-web",
            age_days=400,
        )
    )
    cloud.add(
        Resource(
            id="eip-prod",
            type=ResourceType.EIP,
            region=_REGION,
            name="prod-web-ip",
            monthly_cost_usd=3.0,
            status="in_use",
            attached_to="i-prod-web",
            age_days=400,
        )
    )

    # --- waste: over-provisioned staging instance (4xlarge at 3% CPU) -------
    cloud.add(
        Resource(
            id="i-staging-app",
            type=ResourceType.ECS_INSTANCE,
            region=_REGION,
            name="staging-app",
            monthly_cost_usd=560.0,
            tags={"env": "staging"},
            spec={"instance_type": "ecs.g7.4xlarge"},
            status="running",
            age_days=210,
        ),
        Metrics(resource_id="i-staging-app", avg_cpu_pct=3.2, max_cpu_pct=18.5),
    )

    # --- waste, but protected: oversized production batch box ---------------
    # The detector flags it; the policy gate must block it (env=production).
    cloud.add(
        Resource(
            id="i-prod-batch",
            type=ResourceType.ECS_INSTANCE,
            region=_REGION,
            name="prod-batch",
            monthly_cost_usd=280.0,
            tags={"env": "production"},
            spec={"instance_type": "ecs.c7.2xlarge"},
            status="running",
            age_days=300,
        ),
        Metrics(resource_id="i-prod-batch", avg_cpu_pct=4.0, max_cpu_pct=22.0),
    )

    # --- waste: idle EIP -----------------------------------------------------
    cloud.add(
        Resource(
            id="eip-orphan",
            type=ResourceType.EIP,
            region=_REGION,
            name="old-lb-ip",
            monthly_cost_usd=9.0,
            status="available",
            age_days=150,
        )
    )

    # --- waste: unattached disks --------------------------------------------
    cloud.add(
        Resource(
            id="d-orphan-1",
            type=ResourceType.DISK,
            region=_REGION,
            name="old-data-disk",
            monthly_cost_usd=44.0,
            spec={"size_gb": 500},
            status="available",
            age_days=90,
        )
    )
    cloud.add(
        Resource(
            id="d-orphan-2",
            type=ResourceType.DISK,
            region=_REGION,
            name="migration-temp",
            monthly_cost_usd=18.0,
            spec={"size_gb": 200},
            status="available",
            age_days=45,
        )
    )

    # --- waste: ancient snapshots whose source disk is gone ------------------
    cloud.add(
        Resource(
            id="snap-old-1",
            type=ResourceType.SNAPSHOT,
            region=_REGION,
            name="backup-2024-q3",
            monthly_cost_usd=6.0,
            spec={"source_disk": "d-deleted-long-ago", "size_gb": 300},
            status="available",
            age_days=420,
        )
    )
    cloud.add(
        Resource(
            id="snap-old-2",
            type=ResourceType.SNAPSHOT,
            region=_REGION,
            name="backup-2024-q4",
            monthly_cost_usd=6.0,
            spec={"source_disk": "d-deleted-long-ago", "size_gb": 300},
            status="available",
            age_days=330,
        )
    )

    # --- waste: cold OSS bucket on Standard ----------------------------------
    cloud.add(
        Resource(
            id="oss-archives",
            type=ResourceType.OSS_BUCKET,
            region=_REGION,
            name="company-archives",
            monthly_cost_usd=130.0,
            spec={"storage_class": "Standard"},
            status="in_use",
            age_days=600,
        ),
        Metrics(resource_id="oss-archives", objects_total=80_000, objects_accessed_30d=900),
    )

    return cloud
