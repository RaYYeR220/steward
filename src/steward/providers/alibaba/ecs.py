"""ECS instances, disks, snapshots: raw SDK fetch + pure mappers.

The ``list_*``/mutation functions call the SDK and are covered only by the live
smoke. The ``*_to_resource`` mappers are pure and unit-tested with plain dicts.
"""
from __future__ import annotations

from datetime import datetime

from alibabacloud_ecs20140526 import models as ecs_models
from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_tea_openapi import models as open_api_models

from steward.models import Resource, ResourceType
from steward.providers.alibaba.config import AlibabaConfig
from steward.providers.alibaba.util import age_days_from

_STATUS = {"Running": "running", "Stopped": "stopped", "In_use": "in_use",
           "Available": "available"}


def _status(raw: str) -> str:
    return _STATUS.get(raw, (raw or "").lower())


def make_client(config: AlibabaConfig) -> EcsClient:
    return EcsClient(
        open_api_models.Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            region_id=config.region,
            endpoint=config.ecs_endpoint,
        )
    )


# -- raw fetch (live-only) -----------------------------------------------------


def list_instances(client: EcsClient, region: str) -> list[dict]:
    resp = client.describe_instances(
        ecs_models.DescribeInstancesRequest(region_id=region, page_size=100)
    )
    out: list[dict] = []
    body = resp.body
    instances = body.instances.instance if body.instances else []
    for inst in instances or []:
        tags = {}
        if inst.tags and inst.tags.tag:
            tags = {t.tag_key: t.tag_value for t in inst.tags.tag}
        out.append(
            {
                "id": inst.instance_id,
                "name": inst.instance_name or inst.instance_id,
                "region": inst.region_id,
                "instance_type": inst.instance_type,
                "status": inst.status,
                "creation_time": inst.creation_time,
                "tags": tags,
            }
        )
    return out


def list_disks(client: EcsClient, region: str) -> list[dict]:
    resp = client.describe_disks(
        ecs_models.DescribeDisksRequest(region_id=region, page_size=100)
    )
    out: list[dict] = []
    disks = resp.body.disks.disk if resp.body.disks else []
    for d in disks or []:
        out.append(
            {
                "id": d.disk_id,
                "name": d.disk_name or d.disk_id,
                "region": d.region_id,
                "size_gb": d.size,
                "status": d.status,
                "attached_to": d.instance_id or None,
                "creation_time": d.creation_time,
            }
        )
    return out


def list_snapshots(client: EcsClient, region: str) -> list[dict]:
    resp = client.describe_snapshots(
        ecs_models.DescribeSnapshotsRequest(region_id=region, page_size=100)
    )
    out: list[dict] = []
    snaps = resp.body.snapshots.snapshot if resp.body.snapshots else []
    for s in snaps or []:
        out.append(
            {
                "id": s.snapshot_id,
                "name": s.snapshot_name or s.snapshot_id,
                "region": region,
                "source_disk": s.source_disk_id or None,
                "size_gb": int(s.source_disk_size) if s.source_disk_size else 0,
                "status": s.status,
                "creation_time": s.creation_time,
            }
        )
    return out


# -- pure mappers --------------------------------------------------------------


def instance_to_resource(
    raw: dict, *, cost: float, cost_source: str, now: datetime | None = None
) -> Resource:
    return Resource(
        id=raw["id"],
        type=ResourceType.ECS_INSTANCE,
        region=raw["region"],
        name=raw["name"],
        monthly_cost_usd=cost,
        cost_source=cost_source,
        tags=dict(raw.get("tags") or {}),
        spec={"instance_type": raw["instance_type"]},
        status=_status(raw["status"]),
        age_days=age_days_from(raw.get("creation_time"), now=now),
    )


def disk_to_resource(
    raw: dict, *, cost: float, cost_source: str, now: datetime | None = None
) -> Resource:
    return Resource(
        id=raw["id"],
        type=ResourceType.DISK,
        region=raw["region"],
        name=raw["name"],
        monthly_cost_usd=cost,
        cost_source=cost_source,
        spec={"size_gb": raw.get("size_gb", 0)},
        status=_status(raw["status"]),
        attached_to=raw.get("attached_to"),
        age_days=age_days_from(raw.get("creation_time"), now=now),
    )


def snapshot_to_resource(
    raw: dict, *, cost: float, cost_source: str, now: datetime | None = None
) -> Resource:
    return Resource(
        id=raw["id"],
        type=ResourceType.SNAPSHOT,
        region=raw["region"],
        name=raw["name"],
        monthly_cost_usd=cost,
        cost_source=cost_source,
        spec={"source_disk": raw.get("source_disk"), "size_gb": raw.get("size_gb", 0)},
        status=_status(raw["status"]),
        age_days=age_days_from(raw.get("creation_time"), now=now),
    )


# -- mutations (live-only; guarded in the provider) ----------------------------


def stop_instance(client: EcsClient, instance_id: str) -> None:
    client.stop_instance(
        ecs_models.StopInstanceRequest(instance_id=instance_id, force_stop=False)
    )


def modify_instance_type(client: EcsClient, instance_id: str, instance_type: str) -> None:
    client.modify_instance_spec(
        ecs_models.ModifyInstanceSpecRequest(
            instance_id=instance_id, instance_type=instance_type
        )
    )


def start_instance(client: EcsClient, instance_id: str) -> None:
    client.start_instance(ecs_models.StartInstanceRequest(instance_id=instance_id))


def delete_disk(client: EcsClient, disk_id: str) -> None:
    client.delete_disk(ecs_models.DeleteDiskRequest(disk_id=disk_id))


def delete_snapshot(client: EcsClient, snapshot_id: str) -> None:
    client.delete_snapshot(ecs_models.DeleteSnapshotRequest(snapshot_id=snapshot_id))


def create_snapshot(client: EcsClient, disk_id: str) -> str:
    resp = client.create_snapshot(ecs_models.CreateSnapshotRequest(disk_id=disk_id))
    return resp.body.snapshot_id
