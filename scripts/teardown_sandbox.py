"""Remove everything seed_sandbox.py created (tagged steward-sandbox=true).

Usage (from repo root):
    uv run python scripts/teardown_sandbox.py
"""
from __future__ import annotations

import oss2

from steward.providers.alibaba.config import load_alibaba_config

SANDBOX_BUCKET = "steward-sandbox-archives"


def main() -> None:
    config = load_alibaba_config()
    endpoint = f"https://{config.oss_endpoint}"
    auth = oss2.Auth(config.access_key_id, config.access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, SANDBOX_BUCKET)

    try:
        for obj in oss2.ObjectIterator(bucket):
            bucket.delete_object(obj.key)
        bucket.delete_bucket()
        print(f"deleted bucket {SANDBOX_BUCKET} and its objects")
    except oss2.exceptions.NoSuchBucket:
        print("bucket already gone")


if __name__ == "__main__":
    main()
