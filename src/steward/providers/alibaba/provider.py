"""AlibabaCloudProvider: implements CloudProvider against the live account.

Reads are resilient (a failing service degrades to a partial result with a
warning, never a crashed scan). Cheap/reversible mutations (release EIP, change
OSS storage class) run live. Destructive mutations (ECS resize with downtime,
disk/snapshot deletion) are disabled unless ``allow_destructive`` is True.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from steward.models import Metrics, Resource, ResourceType
from steward.providers.alibaba import ecs, metrics, oss, vpc
from steward.providers.alibaba.config import AlibabaConfig
from steward.providers.alibaba.cost import CostSourcer
from steward.providers.base import CloudError


@contextmanager
def _as_cloud_error(context: str):
    """Re-raise any non-CloudError (raw SDK Tea*/oss2 exceptions) as CloudError.

    The executor only catches CloudError; without this a live SDK failure during
    a mutation would escape as a raw traceback instead of being recorded FAILED.
    """
    try:
        yield
    except CloudError:
        raise
    except Exception as exc:  # noqa: BLE001 — SDK exception boundary
        raise CloudError(f"{context}: {exc}") from exc


class _StaticBill:
    """BillSource backed by a prefetched id->amount map (possibly empty)."""

    def __init__(self, costs: dict[str, float]):
        self._costs = costs

    def monthly_instance_costs(self, billing_cycle: str) -> dict[str, float]:
        return self._costs


def _current_billing_cycle(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


class AlibabaCloudProvider:
    def __init__(
        self,
        config: AlibabaConfig,
        *,
        allow_destructive: bool = False,
        _clients: dict | None = None,
        _bill_costs: dict[str, float] | None = None,
        _fetchers: dict | None = None,
        _mutators: dict | None = None,
    ) -> None:
        self._config = config
        self._allow_destructive = allow_destructive
        self.last_warnings: list[str] = []
        self._cache: dict[str, Resource] = {}

        # Clients (real unless injected for tests).
        self._clients = _clients or {
            "ecs": ecs.make_client(config),
            "vpc": vpc.make_client(config),
            "cms": metrics.make_client(config),
        }
        # Raw fetchers (injectable for tests).
        self._fetchers = _fetchers or {
            "instances": ecs.list_instances,
            "disks": ecs.list_disks,
            "snapshots": ecs.list_snapshots,
            "eips": vpc.list_eips,
            "buckets": oss.list_buckets,
        }
        # Mutators (injectable for tests).
        self._mutators = _mutators or {
            "release_eip": vpc.release_eip,
            "set_oss_class": oss.set_storage_class,
        }
        self._cost = CostSourcer(
            _StaticBill(_bill_costs if _bill_costs is not None else {}),
            billing_cycle=_current_billing_cycle(),
        )

    # -- read ------------------------------------------------------------------

    def list_resources(self) -> list[Resource]:
        self.last_warnings = []
        region = self._config.region
        resources: list[Resource] = []

        def cost_for(kind: str, rid: str, instance_type: str | None):
            return self._cost.monthly_cost(kind, rid, instance_type)

        def section(name: str, fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — resilient discovery
                self.last_warnings.append(f"{name} listing failed: {exc}")

        def instances():
            for raw in self._fetchers["instances"](self._clients["ecs"], region):
                c, src = cost_for("ecs_instance", raw["id"], raw["instance_type"])
                resources.append(ecs.instance_to_resource(raw, cost=c, cost_source=src))

        def disks():
            for raw in self._fetchers["disks"](self._clients["ecs"], region):
                c, src = cost_for("disk", raw["id"], None)
                resources.append(ecs.disk_to_resource(raw, cost=c, cost_source=src))

        def snapshots():
            for raw in self._fetchers["snapshots"](self._clients["ecs"], region):
                c, src = cost_for("snapshot", raw["id"], None)
                resources.append(ecs.snapshot_to_resource(raw, cost=c, cost_source=src))

        def eips():
            for raw in self._fetchers["eips"](self._clients["vpc"], region):
                c, src = cost_for("eip", raw["id"], None)
                resources.append(vpc.eip_to_resource(raw, cost=c, cost_source=src))

        def buckets():
            for raw in self._fetchers["buckets"](self._config):
                c, src = cost_for("oss_bucket", raw["id"], None)
                resources.append(oss.bucket_to_resource(raw, cost=c, cost_source=src))

        for name, fn in (
            ("ecs", instances), ("disk", disks), ("snapshot", snapshots),
            ("eip", eips), ("oss", buckets),
        ):
            section(name, fn)

        self._cache = {r.id: r for r in resources}
        return resources

    def get_resource(self, resource_id: str) -> Resource | None:
        if not self._cache:
            self.list_resources()
        return self._cache.get(resource_id)

    def get_metrics(self, resource_id: str) -> Metrics | None:
        resource = self.get_resource(resource_id)
        if resource is None:
            return None
        if resource.type is ResourceType.ECS_INSTANCE:
            try:
                points = metrics.fetch_cpu(self._clients["cms"], resource_id, 14)
            except Exception:  # noqa: BLE001 — metrics are best-effort
                return None
            return metrics.aggregate_cpu(points, window_days=14, resource_id=resource_id)
        if resource.type is ResourceType.OSS_BUCKET:
            count = resource.spec.get("object_count")
            return oss.bucket_to_metrics({"id": resource_id, "object_count": count or 0})
        return None

    # -- mutations -------------------------------------------------------------

    def release_eip(self, eip_id: str) -> None:
        resource = self.get_resource(eip_id)
        attached = resource.attached_to if resource else None
        with _as_cloud_error(f"release_eip failed for {eip_id}"):
            self._mutators["release_eip"](
                self._clients["vpc"], self._config.region, eip_id, attached
            )

    def set_oss_storage_class(self, bucket_id: str, storage_class: str) -> None:
        with _as_cloud_error(f"set_oss_storage_class failed for {bucket_id}"):
            self._mutators["set_oss_class"](self._config, bucket_id, storage_class)

    def resize_instance(self, instance_id: str, target_instance_type: str) -> None:
        self._guard_destructive("resize_instance")
        ecs.stop_instance(self._clients["ecs"], instance_id)
        ecs.modify_instance_type(self._clients["ecs"], instance_id, target_instance_type)
        ecs.start_instance(self._clients["ecs"], instance_id)

    def delete_disk(self, disk_id: str) -> None:
        self._guard_destructive("delete_disk")
        ecs.delete_disk(self._clients["ecs"], disk_id)

    def delete_snapshot(self, snapshot_id: str) -> None:
        self._guard_destructive("delete_snapshot")
        ecs.delete_snapshot(self._clients["ecs"], snapshot_id)

    def create_snapshot(self, disk_id: str) -> str:
        self._guard_destructive("create_snapshot")
        return ecs.create_snapshot(self._clients["ecs"], disk_id)

    def restore_disk(self, snapshot_id: str) -> str:
        self._guard_destructive("restore_disk")
        raise CloudError("restore_disk is not implemented for the live provider")

    def _guard_destructive(self, action: str) -> None:
        if not self._allow_destructive:
            raise CloudError(
                f"{action} is disabled on the live Alibaba provider; demo "
                "destructive actions on --provider mock, or set "
                "STEWARD_LIVE_DESTRUCTIVE=1"
            )

    # -- verification ----------------------------------------------------------

    def health_check(self, resource_id: str) -> bool:
        resource = self.get_resource(resource_id)
        if resource is None:
            return False
        if resource.type is ResourceType.ECS_INSTANCE:
            # "Survived the action", not "is running": releasing an EIP off an
            # idle (stopped) instance must not be read as the instance breaking.
            # Both running and stopped are healthy steady states. (When live
            # resize is enabled it needs a running-specific post-start check.)
            return resource.status in {"running", "stopped"}
        return True
