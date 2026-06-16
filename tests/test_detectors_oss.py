from steward.detectors import all_detectors, run_detectors
from steward.detectors.oss import OssColdBucketDetector
from steward.models import ActionType, ResourceType
from steward.providers.mock import MockCloud
from steward.testing import make_metrics, make_resource


def cold_bucket_cloud() -> MockCloud:
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "oss-1",
            ResourceType.OSS_BUCKET,
            spec={"storage_class": "Standard"},
            status="in_use",
            monthly_cost_usd=130.0,
        ),
        make_metrics("oss-1", objects_total=80_000, objects_accessed_30d=900),
    )
    return cloud


def test_flags_cold_standard_bucket():
    findings = OssColdBucketDetector().detect(cold_bucket_cloud())
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "oss_cold_bucket"
    assert f.action.type is ActionType.CHANGE_OSS_CLASS
    assert f.action.params == {"target_storage_class": "IA"}
    assert f.monthly_saving_usd == 58.5  # 130 * 0.45
    assert "1.1%" in f.evidence


def test_ignores_bucket_already_on_ia():
    cloud = MockCloud()
    cloud.add(
        make_resource("oss-1", ResourceType.OSS_BUCKET, spec={"storage_class": "IA"}),
        make_metrics("oss-1", objects_total=80_000, objects_accessed_30d=900),
    )
    assert OssColdBucketDetector().detect(cloud) == []


def test_ignores_warm_bucket():
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "oss-1", ResourceType.OSS_BUCKET, spec={"storage_class": "Standard"}
        ),
        make_metrics("oss-1", objects_total=1_000, objects_accessed_30d=400),
    )
    assert OssColdBucketDetector().detect(cloud) == []


def test_ignores_bucket_without_metrics():
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "oss-1", ResourceType.OSS_BUCKET, spec={"storage_class": "Standard"}
        )
    )
    assert OssColdBucketDetector().detect(cloud) == []


def test_registry_lists_all_five_detectors():
    kinds = {d.kind for d in all_detectors()}
    assert kinds == {
        "ecs_overprovisioned",
        "idle_eip",
        "unattached_disk",
        "old_snapshot",
        "oss_cold_bucket",
    }


def test_run_detectors_aggregates_findings():
    findings = run_detectors(cold_bucket_cloud())
    assert [f.kind for f in findings] == ["oss_cold_bucket"]


def test_skips_bucket_when_access_recency_unavailable():
    # The live OSS adapter can't get per-object recency, so objects_accessed_30d
    # is None. The detector must skip (not fabricate "0 accessed") — the agent
    # proposes the change instead.
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "oss-1", ResourceType.OSS_BUCKET, spec={"storage_class": "Standard"}
        ),
        make_metrics("oss-1", objects_total=80_000, objects_accessed_30d=None),
    )
    assert OssColdBucketDetector().detect(cloud) == []
