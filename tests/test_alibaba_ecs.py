from datetime import datetime, timezone

from steward.models import ResourceType
from steward.providers.alibaba.ecs import (
    disk_to_resource,
    instance_to_resource,
    snapshot_to_resource,
)

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)


def test_instance_to_resource():
    raw = {
        "id": "i-1",
        "name": "web",
        "region": "eu-central-1",
        "instance_type": "ecs.g7.large",
        "status": "Running",
        "creation_time": "2026-05-16T00:00:00Z",
        "tags": {"env": "production"},
    }
    res = instance_to_resource(raw, cost=70.0, cost_source="static", now=NOW)
    assert res.id == "i-1"
    assert res.type is ResourceType.ECS_INSTANCE
    assert res.name == "web"
    assert res.status == "running"
    assert res.spec == {"instance_type": "ecs.g7.large"}
    assert res.tags == {"env": "production"}
    assert res.monthly_cost_usd == 70.0
    assert res.cost_source == "static"
    assert res.age_days == 30


def test_instance_status_stopped_maps_through():
    raw = {
        "id": "i-2", "name": "i-2", "region": "eu-central-1",
        "instance_type": "ecs.c7.large", "status": "Stopped",
        "creation_time": "", "tags": {},
    }
    assert instance_to_resource(raw, cost=1.0, cost_source="static", now=NOW).status == "stopped"


def test_disk_to_resource_attached():
    raw = {
        "id": "d-1", "name": "data", "region": "eu-central-1",
        "size_gb": 200, "status": "In_use", "attached_to": "i-1",
        "creation_time": "2026-06-01T00:00:00Z",
    }
    res = disk_to_resource(raw, cost=20.0, cost_source="static", now=NOW)
    assert res.type is ResourceType.DISK
    assert res.attached_to == "i-1"
    assert res.status == "in_use"
    assert res.spec == {"size_gb": 200}
    assert res.age_days == 14


def test_disk_to_resource_unattached():
    raw = {
        "id": "d-2", "name": "d-2", "region": "eu-central-1",
        "size_gb": 50, "status": "Available", "attached_to": None,
        "creation_time": "2026-06-01T00:00:00Z",
    }
    res = disk_to_resource(raw, cost=5.0, cost_source="static", now=NOW)
    assert res.attached_to is None
    assert res.status == "available"


def test_snapshot_to_resource():
    raw = {
        "id": "snap-1", "name": "backup", "region": "eu-central-1",
        "source_disk": "d-gone", "size_gb": 100, "status": "accomplished",
        "creation_time": "2025-06-15T00:00:00Z",
    }
    res = snapshot_to_resource(raw, cost=6.0, cost_source="static", now=NOW)
    assert res.type is ResourceType.SNAPSHOT
    assert res.spec == {"source_disk": "d-gone", "size_gb": 100}
    assert res.age_days == 365
