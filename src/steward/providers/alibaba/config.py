"""Auth + endpoint configuration for the Alibaba Cloud adapter."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from steward.providers.base import CloudError

DEFAULT_REGION = "eu-central-1"
# International billing (BSS) lives on the Singapore endpoint, not the regional one.
BSS_ENDPOINT = "business.ap-southeast-1.aliyuncs.com"


@dataclass(frozen=True)
class AlibabaConfig:
    access_key_id: str
    access_key_secret: str
    region: str = DEFAULT_REGION

    @property
    def ecs_endpoint(self) -> str:
        return f"ecs.{self.region}.aliyuncs.com"

    @property
    def vpc_endpoint(self) -> str:
        return f"vpc.{self.region}.aliyuncs.com"

    @property
    def cms_endpoint(self) -> str:
        return f"metrics.{self.region}.aliyuncs.com"

    @property
    def oss_endpoint(self) -> str:
        return f"oss-{self.region}.aliyuncs.com"

    @property
    def bss_endpoint(self) -> str:
        return BSS_ENDPOINT


def _read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def load_alibaba_config(env_file: Path | None = None) -> AlibabaConfig:
    if env_file is None:
        env_file = Path.cwd() / ".env"
    file_values = _read_env_file(env_file)

    def get(name: str) -> str | None:
        env_val = os.environ.get(name, None)
        if env_val is not None:
            return env_val or None
        return file_values.get(name) or None

    key_id = get("ALIBABA_ACCESS_KEY_ID")
    secret = get("ALIBABA_ACCESS_KEY_SECRET")
    region = get("ALIBABA_REGION") or DEFAULT_REGION
    if not key_id or not secret:
        raise CloudError(
            "ALIBABA_ACCESS_KEY_ID and ALIBABA_ACCESS_KEY_SECRET must be set "
            "(in the environment or .env) to use --provider alibaba"
        )
    return AlibabaConfig(access_key_id=key_id, access_key_secret=secret, region=region)
