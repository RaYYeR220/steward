"""Live, read-only integration test against the real Alibaba Cloud account.

Skipped by default — set ALIBABA_LIVE=1 to run (no charges; read-only).
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("ALIBABA_LIVE"),
    reason="live Alibaba test: set ALIBABA_LIVE=1 to run (read-only, $0)",
)


def test_live_list_resources_and_metrics():
    from steward.models import ResourceType
    from steward.providers.alibaba.config import load_alibaba_config
    from steward.providers.alibaba.provider import AlibabaCloudProvider

    provider = AlibabaCloudProvider(load_alibaba_config())
    resources = provider.list_resources()
    assert isinstance(resources, list)  # may be empty on a fresh account
    assert provider.last_warnings == [] or all(isinstance(w, str) for w in provider.last_warnings)
    for r in resources:
        if r.type is ResourceType.ECS_INSTANCE:
            metrics = provider.get_metrics(r.id)
            assert metrics is None or metrics.window_days == 14
            break
