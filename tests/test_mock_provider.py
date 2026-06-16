import pytest

from steward.models import ResourceType
from steward.providers.base import CloudError
from steward.providers.mock import MockCloud
from steward.testing import make_metrics, make_resource


def make_cloud() -> MockCloud:
    cloud = MockCloud()
    cloud.add(
        make_resource("i-1", spec={"instance_type": "ecs.g7.2xlarge"}),
        make_metrics("i-1", avg_cpu_pct=5.0, max_cpu_pct=20.0),
    )
    cloud.add(make_resource("d-1", ResourceType.DISK, spec={"size_gb": 200}, status="available"))
    cloud.add(make_resource("eip-1", ResourceType.EIP, status="available"))
    cloud.add(
        make_resource(
            "snap-1",
            ResourceType.SNAPSHOT,
            spec={"source_disk": "d-gone", "size_gb": 100},
            status="available",
        )
    )
    cloud.add(
        make_resource("oss-1", ResourceType.OSS_BUCKET, spec={"storage_class": "Standard"})
    )
    return cloud


def test_list_and_get_resources():
    cloud = make_cloud()
    assert len(cloud.list_resources()) == 5
    assert cloud.get_resource("i-1").id == "i-1"
    assert cloud.get_resource("nope") is None


def test_get_metrics():
    cloud = make_cloud()
    assert cloud.get_metrics("i-1").avg_cpu_pct == 5.0
    assert cloud.get_metrics("d-1") is None


def test_resize_instance_updates_spec():
    cloud = make_cloud()
    cloud.resize_instance("i-1", "ecs.g7.xlarge")
    assert cloud.get_resource("i-1").spec["instance_type"] == "ecs.g7.xlarge"


def test_release_eip_removes_resource():
    cloud = make_cloud()
    cloud.release_eip("eip-1")
    assert cloud.get_resource("eip-1") is None


def test_delete_disk_and_snapshot_remove_resources():
    cloud = make_cloud()
    cloud.delete_disk("d-1")
    cloud.delete_snapshot("snap-1")
    assert cloud.get_resource("d-1") is None
    assert cloud.get_resource("snap-1") is None


def test_set_oss_storage_class():
    cloud = make_cloud()
    cloud.set_oss_storage_class("oss-1", "IA")
    assert cloud.get_resource("oss-1").spec["storage_class"] == "IA"


def test_type_mismatch_raises():
    cloud = make_cloud()
    with pytest.raises(CloudError):
        cloud.resize_instance("d-1", "ecs.g7.large")


def test_missing_resource_raises():
    cloud = make_cloud()
    with pytest.raises(CloudError):
        cloud.delete_disk("d-missing")


def test_fail_on_simulates_api_failure():
    cloud = make_cloud()
    cloud.fail_on.add("d-1")
    with pytest.raises(CloudError, match="simulated"):
        cloud.delete_disk("d-1")
    assert cloud.get_resource("d-1") is not None  # nothing changed


def test_snapshot_restore_roundtrip():
    cloud = make_cloud()
    snap_id = cloud.create_snapshot("d-1")
    assert cloud.get_resource(snap_id).spec["source_disk"] == "d-1"
    cloud.delete_disk("d-1")
    assert cloud.get_resource("d-1") is None
    restored_id = cloud.restore_disk(snap_id)
    assert restored_id == "d-1"
    assert cloud.get_resource("d-1").spec["size_gb"] == 200


def test_restore_disk_without_source_raises_cloud_error():
    cloud = make_cloud()
    cloud.add(make_resource("snap-bad", ResourceType.SNAPSHOT, status="available"))
    with pytest.raises(CloudError, match="source_disk"):
        cloud.restore_disk("snap-bad")


def test_health_check():
    cloud = make_cloud()
    assert cloud.health_check("i-1") is True
    cloud.unhealthy.add("i-1")
    assert cloud.health_check("i-1") is False
    assert cloud.health_check("gone-resource") is False
