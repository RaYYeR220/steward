"""Day-1 smoke test for Alibaba Cloud programmatic access (GO/NO-GO gate).

Verifies, in order:
1. the AccessKey works and ECS API is reachable (DescribeRegions),
2. resource enumeration works (DescribeInstances in the target region),
3. OSS access works (list buckets),
4. the billing API is readable (BSS QueryAccountBalance) — Steward's core data source.

Usage (from the steward/ repo root, no project deps touched):
    uv run --with alibabacloud_ecs20140526 --with alibabacloud_bssopenapi20171214 \
           --with oss2 python scripts/smoke_alibaba.py

Reads ALIBABA_ACCESS_KEY_ID / ALIBABA_ACCESS_KEY_SECRET / ALIBABA_REGION from the
environment or from a local .env file.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import oss2
from alibabacloud_bssopenapi20171214.client import Client as BssClient
from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_ecs20140526 import models as ecs_models
from alibabacloud_tea_openapi import models as open_api_models

# International accounts use the Singapore BSS endpoint; the bare one serves
# China-site accounts. Try in this order.
BSS_ENDPOINTS = ["business.ap-southeast-1.aliyuncs.com", "business.aliyuncs.com"]


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("ALIBABA_")})
    missing = [
        k
        for k in ("ALIBABA_ACCESS_KEY_ID", "ALIBABA_ACCESS_KEY_SECRET", "ALIBABA_REGION")
        if not values.get(k)
    ]
    if missing:
        sys.exit(f"Missing in env/.env: {', '.join(missing)}. Aborting.")
    return values


def smoke_ecs(env: dict[str, str]) -> None:
    region = env["ALIBABA_REGION"]
    config = open_api_models.Config(
        access_key_id=env["ALIBABA_ACCESS_KEY_ID"],
        access_key_secret=env["ALIBABA_ACCESS_KEY_SECRET"],
        region_id=region,
        endpoint=f"ecs.{region}.aliyuncs.com",
    )
    client = EcsClient(config)

    t0 = time.perf_counter()
    regions = client.describe_regions(ecs_models.DescribeRegionsRequest())
    dt = time.perf_counter() - t0
    count = len(regions.body.regions.region)
    print(f"[1/4] ECS DescribeRegions OK in {dt:.2f}s — {count} regions visible")

    t0 = time.perf_counter()
    instances = client.describe_instances(
        ecs_models.DescribeInstancesRequest(region_id=region, page_size=50)
    )
    dt = time.perf_counter() - t0
    total = instances.body.total_count
    print(f"[2/4] ECS DescribeInstances({region}) OK in {dt:.2f}s — {total} instances")


def smoke_oss(env: dict[str, str]) -> None:
    region = env["ALIBABA_REGION"]
    auth = oss2.Auth(env["ALIBABA_ACCESS_KEY_ID"], env["ALIBABA_ACCESS_KEY_SECRET"])
    service = oss2.Service(auth, f"https://oss-{region}.aliyuncs.com")
    t0 = time.perf_counter()
    buckets = [b.name for b in oss2.BucketIterator(service)]
    dt = time.perf_counter() - t0
    print(f"[3/4] OSS list buckets OK in {dt:.2f}s — {len(buckets)} buckets")


def smoke_billing(env: dict[str, str]) -> None:
    last_error: Exception | None = None
    for endpoint in BSS_ENDPOINTS:
        config = open_api_models.Config(
            access_key_id=env["ALIBABA_ACCESS_KEY_ID"],
            access_key_secret=env["ALIBABA_ACCESS_KEY_SECRET"],
            endpoint=endpoint,
        )
        client = BssClient(config)
        try:
            t0 = time.perf_counter()
            balance = client.query_account_balance()
            dt = time.perf_counter() - t0
            data = balance.body.data
            print(
                f"[4/4] BSS QueryAccountBalance OK in {dt:.2f}s via {endpoint} — "
                f"available: {data.available_amount} {data.currency}"
            )
            return
        except Exception as exc:  # noqa: BLE001 — endpoint probing
            last_error = exc
            continue
    sys.exit(f"[4/4] FAILED: billing API unreachable on all endpoints: {last_error}")


def main() -> None:
    env = load_env()
    smoke_ecs(env)
    smoke_oss(env)
    smoke_billing(env)
    print("\nGO: Alibaba Cloud programmatic access works (ECS + OSS + billing).")


if __name__ == "__main__":
    main()
