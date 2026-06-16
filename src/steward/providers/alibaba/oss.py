"""OSS buckets: raw fetch (oss2) + pure mappers + storage-class transition.

Per-object access recency is not cheaply available, so ``bucket_to_metrics``
leaves ``objects_accessed_30d`` as None: the deterministic OSS detector skips
live buckets and the Qwen agent proposes the storage-class change instead.
"""
from __future__ import annotations

from datetime import datetime

import oss2

from steward.models import Metrics, Resource, ResourceType
from steward.providers.alibaba.config import AlibabaConfig
from steward.providers.alibaba.util import age_days_from


def make_auth(config: AlibabaConfig) -> oss2.Auth:
    return oss2.Auth(config.access_key_id, config.access_key_secret)


def _endpoint(config: AlibabaConfig) -> str:
    return f"https://{config.oss_endpoint}"


def list_buckets(config: AlibabaConfig) -> list[dict]:
    auth = make_auth(config)
    service = oss2.Service(auth, _endpoint(config))
    out: list[dict] = []
    for b in oss2.BucketIterator(service):
        bucket = oss2.Bucket(auth, _endpoint(config), b.name)
        info = bucket.get_bucket_info()
        stat = bucket.get_bucket_stat()
        out.append(
            {
                "id": b.name,
                "name": b.name,
                "region": config.region,
                "storage_class": info.storage_class,
                "creation_time": b.creation_date,  # epoch seconds or ISO depending on SDK
                "object_count": stat.object_count,
                "storage_bytes": stat.storage_size_in_bytes,
            }
        )
    return out


def bucket_to_resource(
    raw: dict, *, cost: float, cost_source: str, now: datetime | None = None
) -> Resource:
    created = raw.get("creation_time")
    if isinstance(created, (int, float)):
        created = datetime.utcfromtimestamp(created).isoformat()
    return Resource(
        id=raw["id"],
        type=ResourceType.OSS_BUCKET,
        region=raw["region"],
        name=raw["name"],
        monthly_cost_usd=cost,
        cost_source=cost_source,
        spec={
            "storage_class": raw["storage_class"],
            "object_count": raw.get("object_count", 0),
        },
        status="in_use",
        age_days=age_days_from(created, now=now),
    )


def bucket_to_metrics(raw: dict) -> Metrics:
    return Metrics(
        resource_id=raw.get("id", ""),
        objects_total=raw.get("object_count", 0),
        objects_accessed_30d=None,
    )


def set_storage_class(config: AlibabaConfig, bucket_name: str, storage_class: str) -> None:
    """Add a lifecycle rule transitioning all objects to ``storage_class``.

    Reversible: re-set the rule with a different target class, or delete it.
    """
    auth = make_auth(config)
    bucket = oss2.Bucket(auth, _endpoint(config), bucket_name)
    rule = oss2.models.LifecycleRule(
        "steward-transition",
        prefix="",
        status=oss2.models.LifecycleRule.ENABLED,
        storage_transitions=[
            # OSS requires a positive Days; 1 is the practical minimum ("next day").
            oss2.models.StorageTransition(
                days=1, storage_class=storage_class
            )
        ],
    )
    bucket.put_bucket_lifecycle(oss2.models.BucketLifecycle([rule]))
