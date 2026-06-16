import pytest

from steward.models import ResourceType
from steward.providers.alibaba.config import AlibabaConfig
from steward.providers.alibaba.provider import AlibabaCloudProvider
from steward.providers.base import CloudError

CFG = AlibabaConfig(access_key_id="ak", access_key_secret="sk", region="eu-central-1")


class FakeServices:
    """Stand-in for the raw fetch + mutation functions the provider calls."""

    def __init__(self):
        self.released = []
        self.oss_classed = []
        self.instances = [
            {
                "id": "i-1", "name": "staging", "region": "eu-central-1",
                "instance_type": "ecs.g7.4xlarge", "status": "Running",
                "creation_time": "2026-01-01T00:00:00Z", "tags": {},
            }
        ]
        self.disks = [
            {
                "id": "d-1", "name": "d-1", "region": "eu-central-1", "size_gb": 200,
                "status": "Available", "attached_to": None,
                "creation_time": "2026-01-01T00:00:00Z",
            }
        ]
        self.snapshots = []
        self.eips = [
            {
                "id": "eip-1", "name": "eip-1", "region": "eu-central-1",
                "status": "Available", "attached_to": None, "creation_time": "",
            }
        ]
        self.buckets = [
            {
                "id": "b-1", "name": "b-1", "region": "eu-central-1",
                "storage_class": "Standard", "creation_time": "2026-01-01T00:00:00Z",
                "object_count": 100, "storage_bytes": 1024,
            }
        ]


def _raise(exc):
    def _fn(*args, **kwargs):
        raise exc

    return _fn


def build_provider(services=None, *, allow_destructive=False, fail_eip=False):
    services = services or FakeServices()
    eips_fetcher = (
        _raise(CloudError("eip api down")) if fail_eip else (lambda c, r: services.eips)
    )
    provider = AlibabaCloudProvider(
        CFG,
        allow_destructive=allow_destructive,
        _clients={"ecs": object(), "vpc": object(), "cms": object()},
        _bill_costs={},  # empty bill -> static costs
        _fetchers={
            "instances": lambda c, r: services.instances,
            "disks": lambda c, r: services.disks,
            "snapshots": lambda c, r: services.snapshots,
            "eips": eips_fetcher,
            "buckets": lambda cfg: services.buckets,
        },
        _mutators={
            "release_eip": lambda c, r, eip, att: services.released.append(eip),
            "set_oss_class": lambda cfg, b, cls: services.oss_classed.append((b, cls)),
        },
    )
    return provider, services


def test_list_resources_aggregates_all_kinds():
    provider, _ = build_provider()
    kinds = {r.type for r in provider.list_resources()}
    assert kinds == {
        ResourceType.ECS_INSTANCE,
        ResourceType.DISK,
        ResourceType.EIP,
        ResourceType.OSS_BUCKET,
    }


def test_costs_are_static_on_empty_bill():
    provider, _ = build_provider()
    inst = next(r for r in provider.list_resources() if r.type is ResourceType.ECS_INSTANCE)
    assert inst.cost_source == "static"
    assert inst.monthly_cost_usd == 560.0  # ecs.g7.4xlarge static price


def test_failing_service_yields_partial_results_and_warning():
    provider, _ = build_provider(fail_eip=True)
    resources = provider.list_resources()
    assert all(r.type is not ResourceType.EIP for r in resources)
    assert any("eip" in w.lower() for w in provider.last_warnings)


def test_get_resource_finds_by_id():
    provider, _ = build_provider()
    provider.list_resources()
    assert provider.get_resource("i-1").id == "i-1"
    assert provider.get_resource("nope") is None


def test_release_eip_is_live():
    provider, services = build_provider()
    provider.list_resources()
    provider.release_eip("eip-1")
    assert services.released == ["eip-1"]


def test_set_oss_storage_class_is_live():
    provider, services = build_provider()
    provider.set_oss_storage_class("b-1", "IA")
    assert services.oss_classed == [("b-1", "IA")]


def test_destructive_actions_blocked_by_default():
    provider, _ = build_provider()
    with pytest.raises(CloudError, match="disabled on the live"):
        provider.delete_disk("d-1")
    with pytest.raises(CloudError, match="disabled on the live"):
        provider.resize_instance("i-1", "ecs.g7.2xlarge")
    with pytest.raises(CloudError, match="disabled on the live"):
        provider.delete_snapshot("snap-1")


def test_health_check_reflects_presence():
    provider, _ = build_provider()
    provider.list_resources()
    assert provider.health_check("i-1") is True
    assert provider.health_check("ghost") is False


def test_health_check_treats_stopped_instance_as_survived():
    # An EIP released off an idle (stopped) instance must not read as the
    # instance breaking: stopped is a healthy steady state, not a failure.
    services = FakeServices()
    services.instances[0]["status"] = "Stopped"
    provider, _ = build_provider(services)
    provider.list_resources()
    assert provider.health_check("i-1") is True


def test_live_mutation_sdk_error_is_wrapped_as_cloud_error():
    services = FakeServices()
    provider, _ = build_provider(services)
    provider._mutators["release_eip"] = _raise(RuntimeError("Tea: throttled"))
    provider.list_resources()
    with pytest.raises(CloudError, match="release_eip failed for eip-1"):
        provider.release_eip("eip-1")


def test_live_oss_mutation_sdk_error_is_wrapped_as_cloud_error():
    services = FakeServices()
    provider, _ = build_provider(services)
    provider._mutators["set_oss_class"] = _raise(RuntimeError("oss2: conflict"))
    with pytest.raises(CloudError, match="set_oss_storage_class failed for b-1"):
        provider.set_oss_storage_class("b-1", "IA")
