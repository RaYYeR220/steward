"""Elastic IPs: raw SDK fetch + pure mapper + release mutation (live-only)."""
from __future__ import annotations

import time
from datetime import datetime

from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_vpc20160428 import models as vpc_models
from alibabacloud_vpc20160428.client import Client as VpcClient

from steward.models import Resource, ResourceType
from steward.providers.alibaba.config import AlibabaConfig
from steward.providers.alibaba.util import age_days_from

_STATUS = {"InUse": "in_use", "Available": "available", "Associating": "in_use",
           "Unassociating": "available"}


def make_client(config: AlibabaConfig) -> VpcClient:
    return VpcClient(
        open_api_models.Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            region_id=config.region,
            endpoint=config.vpc_endpoint,
        )
    )


def list_eips(client: VpcClient, region: str) -> list[dict]:
    resp = client.describe_eip_addresses(
        vpc_models.DescribeEipAddressesRequest(region_id=region, page_size=100)
    )
    out: list[dict] = []
    eips = resp.body.eip_addresses.eip_address if resp.body.eip_addresses else []
    for e in eips or []:
        out.append(
            {
                "id": e.allocation_id,
                "name": e.name or e.ip_address or e.allocation_id,
                "region": region,
                "status": e.status,
                "attached_to": e.instance_id or None,
                "creation_time": e.allocation_time,
            }
        )
    return out


def eip_to_resource(
    raw: dict, *, cost: float, cost_source: str, now: datetime | None = None
) -> Resource:
    return Resource(
        id=raw["id"],
        type=ResourceType.EIP,
        region=raw["region"],
        name=raw["name"],
        monthly_cost_usd=cost,
        cost_source=cost_source,
        status=_STATUS.get(raw["status"], (raw["status"] or "").lower()),
        attached_to=raw.get("attached_to"),
        age_days=age_days_from(raw.get("creation_time"), now=now),
    )


def release_eip(client: VpcClient, region: str, eip_id: str, attached_to: str | None) -> None:
    if attached_to:
        client.unassociate_eip_address(
            vpc_models.UnassociateEipAddressRequest(
                region_id=region, allocation_id=eip_id, instance_id=attached_to
            )
        )
        time.sleep(2)  # release rejects until the EIP leaves Unassociating
    client.release_eip_address(
        vpc_models.ReleaseEipAddressRequest(region_id=region, allocation_id=eip_id)
    )
