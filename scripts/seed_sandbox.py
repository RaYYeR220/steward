"""Populate the live account with deliberately-wasteful FREE-TIER resources.

Default: one OSS bucket on Standard storage with a few small cold objects
(within the 500 GB free trial), tagged steward-sandbox=true. An idle EIP (small
hourly charge) is opt-in via --with-eip.

Usage (from repo root):
    uv run python scripts/seed_sandbox.py [--with-eip]
"""
from __future__ import annotations

import argparse

import oss2

from steward.providers.alibaba.config import load_alibaba_config

SANDBOX_BUCKET = "steward-sandbox-archives"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-eip", action="store_true", help="also allocate an idle EIP (small charge)")
    args = parser.parse_args()

    config = load_alibaba_config()
    endpoint = f"https://{config.oss_endpoint}"
    auth = oss2.Auth(config.access_key_id, config.access_key_secret)

    bucket = oss2.Bucket(auth, endpoint, SANDBOX_BUCKET)
    try:
        bucket.create_bucket(oss2.models.BUCKET_ACL_PRIVATE)
        print(f"created bucket {SANDBOX_BUCKET} (Standard)")
    except oss2.exceptions.ServerError as exc:
        if getattr(exc, "code", "") == "BucketAlreadyExists" or exc.status == 409:
            print(f"bucket {SANDBOX_BUCKET} already exists; reusing it")
        elif exc.status == 403:
            raise SystemExit(
                "OSS rejected the request (403). The OSS service is likely not "
                "activated on this account — enable it once at "
                "https://oss.console.aliyun.com (free), then re-run."
            )
        else:
            raise

    tagging = oss2.models.Tagging()
    tagging.tag_set.add("steward-sandbox", "true")
    bucket.put_bucket_tagging(tagging)
    for i in range(5):
        bucket.put_object(f"cold/object-{i}.txt", b"steward sandbox cold object\n")
    print("wrote 5 cold objects + steward-sandbox tag")

    if args.with_eip:
        print("--with-eip: allocate one EIP via the VPC console or extend this "
              "script; left manual to avoid an accidental standing charge.")


if __name__ == "__main__":
    main()
