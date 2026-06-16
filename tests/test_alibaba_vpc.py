from datetime import datetime, timezone

from steward.models import ResourceType
from steward.providers.alibaba.vpc import eip_to_resource

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)


def test_eip_to_resource_idle():
    raw = {
        "id": "eip-1", "name": "old-lb", "region": "eu-central-1",
        "status": "Available", "attached_to": None,
        "creation_time": "2026-01-16T00:00:00Z",
    }
    res = eip_to_resource(raw, cost=9.0, cost_source="static", now=NOW)
    assert res.type is ResourceType.EIP
    assert res.status == "available"
    assert res.attached_to is None
    assert res.monthly_cost_usd == 9.0


def test_eip_to_resource_in_use():
    raw = {
        "id": "eip-2", "name": "eip-2", "region": "eu-central-1",
        "status": "InUse", "attached_to": "i-1", "creation_time": "",
    }
    res = eip_to_resource(raw, cost=9.0, cost_source="static", now=NOW)
    assert res.status == "in_use"
    assert res.attached_to == "i-1"
