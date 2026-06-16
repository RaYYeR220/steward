"""In-memory cloud for tests and demos.

Simulation knobs:
- ``fail_on``: resource ids whose mutations raise CloudError (API failure demo)
- ``unhealthy``: resource ids that fail health_check (rollback demo)
"""
from __future__ import annotations

import itertools
from dataclasses import replace

from steward.models import Metrics, Resource, ResourceType
from steward.providers.base import CloudError, CloudProvider


class MockCloud:
    """In-memory CloudProvider. Knobs: ``fail_on`` (mutations raise), ``unhealthy`` (health_check fails)."""

    def __init__(self) -> None:
        self._resources: dict[str, Resource] = {}
        self._metrics: dict[str, Metrics] = {}
        self.fail_on: set[str] = set()
        self.unhealthy: set[str] = set()
        self._snap_counter = itertools.count(1)

    # -- setup ----------------------------------------------------------------
    def add(self, resource: Resource, metrics: Metrics | None = None) -> None:
        self._resources[resource.id] = resource
        if metrics is not None:
            self._metrics[resource.id] = metrics

    # -- read -------------------------------------------------------------------
    def list_resources(self) -> list[Resource]:
        return list(self._resources.values())

    def get_resource(self, resource_id: str) -> Resource | None:
        return self._resources.get(resource_id)

    def get_metrics(self, resource_id: str) -> Metrics | None:
        return self._metrics.get(resource_id)

    # -- internals ----------------------------------------------------------------
    def _require(self, resource_id: str, expected: ResourceType) -> Resource:
        res = self._resources.get(resource_id)
        if res is None:
            raise CloudError(f"no such resource: {resource_id}")
        if res.type is not expected:
            raise CloudError(
                f"{resource_id} is {res.type.value}, expected {expected.value}"
            )
        return res

    def _check_failure(self, resource_id: str) -> None:
        if resource_id in self.fail_on:
            raise CloudError(f"simulated API failure for {resource_id}")

    # -- mutations ----------------------------------------------------------------
    def resize_instance(self, instance_id: str, target_instance_type: str) -> None:
        current = self._require(instance_id, ResourceType.ECS_INSTANCE)
        self._check_failure(instance_id)
        spec = dict(current.spec) | {"instance_type": target_instance_type}
        self._resources[instance_id] = replace(current, spec=spec)

    def release_eip(self, eip_id: str) -> None:
        self._require(eip_id, ResourceType.EIP)
        self._check_failure(eip_id)
        del self._resources[eip_id]

    def delete_disk(self, disk_id: str) -> None:
        self._require(disk_id, ResourceType.DISK)
        self._check_failure(disk_id)
        del self._resources[disk_id]

    def delete_snapshot(self, snapshot_id: str) -> None:
        self._require(snapshot_id, ResourceType.SNAPSHOT)
        self._check_failure(snapshot_id)
        del self._resources[snapshot_id]

    def set_oss_storage_class(self, bucket_id: str, storage_class: str) -> None:
        current = self._require(bucket_id, ResourceType.OSS_BUCKET)
        self._check_failure(bucket_id)
        spec = dict(current.spec) | {"storage_class": storage_class}
        self._resources[bucket_id] = replace(current, spec=spec)

    def create_snapshot(self, disk_id: str) -> str:
        disk = self._require(disk_id, ResourceType.DISK)
        self._check_failure(disk_id)
        snap_id = f"snap-rollback-{next(self._snap_counter)}"
        self._resources[snap_id] = Resource(
            id=snap_id,
            type=ResourceType.SNAPSHOT,
            region=disk.region,
            name=f"rollback-snapshot-of-{disk.id}",
            monthly_cost_usd=0.0,
            spec={"source_disk": disk.id, "size_gb": disk.spec.get("size_gb", 0)},
            status="available",
        )
        return snap_id

    def restore_disk(self, snapshot_id: str) -> str:
        snap = self._require(snapshot_id, ResourceType.SNAPSHOT)
        self._check_failure(snapshot_id)
        disk_id = snap.spec.get("source_disk")
        if disk_id is None:
            raise CloudError(f"snapshot {snapshot_id} has no source_disk in spec")
        # Billing fields are not restored; rollback only needs the disk to
        # exist again and be healthy.
        self._resources[disk_id] = Resource(
            id=disk_id,
            type=ResourceType.DISK,
            region=snap.region,
            name=f"restored-{disk_id}",
            monthly_cost_usd=0.0,
            spec={"size_gb": snap.spec.get("size_gb", 0)},
            status="available",
        )
        return disk_id

    # -- verification ---------------------------------------------------------------
    def health_check(self, resource_id: str) -> bool:
        return resource_id in self._resources and resource_id not in self.unhealthy


# Structural check: fails type-checking (and import wiring) if MockCloud drifts
# from the CloudProvider protocol.
_PROTOCOL_CHECK: CloudProvider = MockCloud()
