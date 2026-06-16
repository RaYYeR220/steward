from steward.detectors.storage import OldSnapshotDetector, UnattachedDiskDetector
from steward.models import ActionType, ResourceType
from steward.providers.mock import MockCloud
from steward.testing import make_resource


def test_flags_old_unattached_disk():
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "d-1", ResourceType.DISK, status="available", age_days=90, monthly_cost_usd=44.0
        )
    )
    findings = UnattachedDiskDetector().detect(cloud)
    assert len(findings) == 1
    assert findings[0].kind == "unattached_disk"
    assert findings[0].action.type is ActionType.DELETE_DISK
    assert findings[0].monthly_saving_usd == 44.0


def test_ignores_recently_created_unattached_disk():
    cloud = MockCloud()
    cloud.add(make_resource("d-1", ResourceType.DISK, status="available", age_days=3))
    assert UnattachedDiskDetector().detect(cloud) == []


def test_ignores_attached_disk():
    cloud = MockCloud()
    cloud.add(make_resource("i-1"))
    cloud.add(
        make_resource(
            "d-1", ResourceType.DISK, status="in_use", attached_to="i-1", age_days=400
        )
    )
    assert UnattachedDiskDetector().detect(cloud) == []


def test_flags_old_snapshot_with_deleted_source_disk():
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "snap-1",
            ResourceType.SNAPSHOT,
            spec={"source_disk": "d-gone"},
            age_days=400,
            monthly_cost_usd=6.0,
        )
    )
    findings = OldSnapshotDetector().detect(cloud)
    assert len(findings) == 1
    assert findings[0].kind == "old_snapshot"
    assert findings[0].action.type is ActionType.DELETE_SNAPSHOT
    assert "source disk no longer exists" in findings[0].evidence


def test_keeps_old_snapshot_whose_disk_still_exists():
    cloud = MockCloud()
    cloud.add(make_resource("d-1", ResourceType.DISK, status="in_use", age_days=500))
    cloud.add(
        make_resource(
            "snap-1", ResourceType.SNAPSHOT, spec={"source_disk": "d-1"}, age_days=400
        )
    )
    assert OldSnapshotDetector().detect(cloud) == []


def test_keeps_young_snapshot():
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "snap-1", ResourceType.SNAPSHOT, spec={"source_disk": "d-gone"}, age_days=30
        )
    )
    assert OldSnapshotDetector().detect(cloud) == []


def test_keeps_old_snapshot_without_source_disk_key():
    cloud = MockCloud()
    cloud.add(make_resource("snap-1", ResourceType.SNAPSHOT, age_days=400))
    assert OldSnapshotDetector().detect(cloud) == []
