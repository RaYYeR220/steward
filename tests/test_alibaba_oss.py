from datetime import datetime, timezone

from steward.models import ResourceType
from steward.providers.alibaba.oss import bucket_to_metrics, bucket_to_resource

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)


def test_bucket_to_resource():
    raw = {
        "id": "company-archives", "name": "company-archives",
        "region": "eu-central-1", "storage_class": "Standard",
        "creation_time": "2024-10-23T00:00:00Z",
    }
    res = bucket_to_resource(raw, cost=25.0, cost_source="static", now=NOW)
    assert res.type is ResourceType.OSS_BUCKET
    assert res.spec["storage_class"] == "Standard"
    assert res.spec["object_count"] == 0  # not provided in this raw stub
    assert res.status == "in_use"
    assert res.monthly_cost_usd == 25.0
    assert res.age_days == 600


def test_bucket_to_metrics_has_count_but_no_access_recency():
    metrics = bucket_to_metrics({"object_count": 80_000})
    assert metrics.objects_total == 80_000
    # per-object access recency is not cheaply available from OSS
    assert metrics.objects_accessed_30d is None


def test_bucket_to_metrics_zero_objects():
    assert bucket_to_metrics({"object_count": 0}).objects_total == 0
