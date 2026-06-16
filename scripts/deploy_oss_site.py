"""Deploy the built dashboard SPA (dashboard/dist) to Alibaba OSS static hosting.

$0 / free-tier: a tiny public-read bucket with static website hosting. The SPA
runs in static mode (bundled sample-snapshot.json), so no backend is required —
this gives a public, Alibaba-hosted demo URL.

Reuses the project's Alibaba creds (.env) and the oss2 SDK already in deps.

Usage (from repo root):
    uv run python scripts/deploy_oss_site.py
    uv run python scripts/deploy_oss_site.py --bucket my-bucket-name
"""
from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

import oss2

from steward.providers.alibaba.config import load_alibaba_config

DEFAULT_BUCKET = "steward-finops-dashboard"
DIST = Path("dashboard/dist")

# content types Vite emits that mimetypes may miss / get wrong on Windows
EXTRA_TYPES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".map": "application/json",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
}


def _content_type(path: Path) -> str:
    if path.suffix in EXTRA_TYPES:
        return EXTRA_TYPES[path.suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    args = parser.parse_args()

    if not DIST.is_dir() or not (DIST / "index.html").exists():
        print(f"ERROR: {DIST}/index.html not found — run `npm run build` in dashboard/ first.")
        return 1

    cfg = load_alibaba_config()
    endpoint = f"https://oss-{cfg.region}.aliyuncs.com"
    auth = oss2.Auth(cfg.access_key_id, cfg.access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, args.bucket)

    # 1. create the bucket (public-read) if it isn't ours already
    try:
        bucket.create_bucket(oss2.BUCKET_ACL_PUBLIC_READ)
        print(f"created bucket {args.bucket} in {cfg.region}")
    except oss2.exceptions.ServerError as exc:
        if exc.code in ("BucketAlreadyExists", "BucketAlreadyOwnedByYou"):
            # already exists — make sure it's ours and public-read
            try:
                bucket.put_bucket_acl(oss2.BUCKET_ACL_PUBLIC_READ)
                print(f"reusing existing bucket {args.bucket} (set public-read)")
            except oss2.exceptions.OssError as inner:
                print(
                    f"ERROR: bucket {args.bucket!r} exists but isn't accessible "
                    f"({inner.code}). Pick another --bucket name."
                )
                return 1
        else:
            print(f"ERROR creating bucket: {exc.code}: {exc.message}")
            print(
                "If this is AccessDenied/Block-Public-Access, disable 'Block Public "
                "Access' for the bucket in the OSS console, then re-run."
            )
            return 1

    # 2. static website hosting: index + SPA error fallback both -> index.html
    bucket.put_bucket_website(oss2.models.BucketWebsite("index.html", "index.html"))
    print("enabled static website hosting (index.html)")

    # 3. upload every file in dist/ with the right content type
    count = 0
    for path in sorted(DIST.rglob("*")):
        if path.is_dir():
            continue
        key = path.relative_to(DIST).as_posix()
        bucket.put_object_from_file(
            key, str(path), headers={"Content-Type": _content_type(path)}
        )
        count += 1
        print(f"  uploaded {key}")
    print(f"uploaded {count} files")

    site = f"http://{args.bucket}.oss-website-{cfg.region}.aliyuncs.com"
    direct = f"https://{args.bucket}.oss-{cfg.region}.aliyuncs.com/index.html"
    print("\nDeployed. Public URLs:")
    print(f"  website hosting : {site}")
    print(f"  direct object   : {direct}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
