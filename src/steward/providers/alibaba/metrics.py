"""ECS CPU metrics from CloudMonitor: raw fetch + pure aggregator.

DescribeMetricList returns hourly datapoints, each already carrying Average and
Maximum. We reduce them to a single avg/max over the window. Agentless — basic
CPUUtilization is hypervisor-level, no probe required.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from alibabacloud_cms20190101 import models as cms_models
from alibabacloud_cms20190101.client import Client as CmsClient
from alibabacloud_tea_openapi import models as open_api_models

from steward.models import Metrics
from steward.providers.alibaba.config import AlibabaConfig


def make_client(config: AlibabaConfig) -> CmsClient:
    return CmsClient(
        open_api_models.Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            region_id=config.region,
            endpoint=config.cms_endpoint,
        )
    )


def fetch_cpu(
    client: CmsClient, instance_id: str, window_days: int, now: datetime | None = None
) -> list[dict]:
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)
    resp = client.describe_metric_list(
        cms_models.DescribeMetricListRequest(
            namespace="acs_ecs_dashboard",
            metric_name="CPUUtilization",
            period="3600",
            start_time=str(int(start.timestamp() * 1000)),
            end_time=str(int(end.timestamp() * 1000)),
            dimensions=json.dumps([{"instanceId": instance_id}]),
        )
    )
    raw = resp.body.datapoints
    return json.loads(raw) if raw else []


def aggregate_cpu(datapoints: list[dict], window_days: int, resource_id: str) -> Metrics:
    averages = [d["Average"] for d in datapoints if "Average" in d]
    maxima = [d["Maximum"] for d in datapoints if "Maximum" in d]
    avg = round(sum(averages) / len(averages), 2) if averages else None
    mx = round(max(maxima), 2) if maxima else None
    return Metrics(
        resource_id=resource_id,
        window_days=window_days,
        avg_cpu_pct=avg,
        max_cpu_pct=mx,
    )
