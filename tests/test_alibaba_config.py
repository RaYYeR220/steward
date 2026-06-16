import pytest

from steward.providers.alibaba.config import AlibabaConfig, load_alibaba_config
from steward.providers.base import CloudError


def test_endpoints_derive_from_region():
    cfg = AlibabaConfig(access_key_id="ak", access_key_secret="sk", region="eu-central-1")
    assert cfg.ecs_endpoint == "ecs.eu-central-1.aliyuncs.com"
    assert cfg.vpc_endpoint == "vpc.eu-central-1.aliyuncs.com"
    assert cfg.cms_endpoint == "metrics.eu-central-1.aliyuncs.com"
    assert cfg.oss_endpoint == "oss-eu-central-1.aliyuncs.com"
    assert cfg.bss_endpoint == "business.ap-southeast-1.aliyuncs.com"


def test_load_reads_env_file(tmp_path, monkeypatch):
    for name in ("ALIBABA_ACCESS_KEY_ID", "ALIBABA_ACCESS_KEY_SECRET", "ALIBABA_REGION"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        'ALIBABA_ACCESS_KEY_ID="ak-123"\nALIBABA_ACCESS_KEY_SECRET=sk-456\n'
        "ALIBABA_REGION=eu-central-1\n",
        encoding="utf-8",
    )
    cfg = load_alibaba_config(env)
    assert cfg.access_key_id == "ak-123"
    assert cfg.access_key_secret == "sk-456"
    assert cfg.region == "eu-central-1"


def test_process_env_wins_over_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ALIBABA_ACCESS_KEY_ID=from-file\n", encoding="utf-8")
    monkeypatch.setenv("ALIBABA_ACCESS_KEY_ID", "from-env")
    monkeypatch.setenv("ALIBABA_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setenv("ALIBABA_REGION", "eu-central-1")
    assert load_alibaba_config(env).access_key_id == "from-env"


def test_missing_keys_raise_cloud_error(tmp_path, monkeypatch):
    for name in ("ALIBABA_ACCESS_KEY_ID", "ALIBABA_ACCESS_KEY_SECRET", "ALIBABA_REGION"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(CloudError, match="ALIBABA_ACCESS_KEY_ID"):
        load_alibaba_config(tmp_path / "missing.env")


def test_region_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("ALIBABA_REGION", raising=False)
    monkeypatch.setenv("ALIBABA_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIBABA_ACCESS_KEY_SECRET", "sk")
    assert load_alibaba_config(tmp_path / "x.env").region == "eu-central-1"
