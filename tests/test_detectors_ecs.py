from steward.detectors.ecs import EcsOverprovisionedDetector
from steward.models import ActionType
from steward.providers.mock import MockCloud
from steward.testing import make_metrics, make_resource


def cloud_with_instance(*, status="running", instance_type="ecs.g7.2xlarge", metrics=None):
    cloud = MockCloud()
    cloud.add(
        make_resource(
            "i-1",
            spec={"instance_type": instance_type},
            monthly_cost_usd=300.0,
            status=status,
        ),
        metrics,
    )
    return cloud


def test_flags_idle_oversized_instance():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", avg_cpu_pct=3.0, max_cpu_pct=15.0)
    )
    findings = EcsOverprovisionedDetector().detect(cloud)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "ecs_overprovisioned"
    assert f.action.type is ActionType.RESIZE_ECS
    assert f.action.params == {"target_instance_type": "ecs.g7.xlarge"}
    assert f.monthly_saving_usd == 150.0  # one size down ~= half the cost
    assert "3.0%" in f.evidence


def test_ignores_busy_instance():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", avg_cpu_pct=45.0, max_cpu_pct=90.0)
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_ignores_high_peak_even_with_low_average():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", avg_cpu_pct=5.0, max_cpu_pct=85.0)
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_ignores_stopped_instance():
    cloud = cloud_with_instance(
        status="stopped",
        metrics=make_metrics("i-1", avg_cpu_pct=0.0, max_cpu_pct=0.0),
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_ignores_instance_without_metrics():
    cloud = cloud_with_instance(metrics=None)
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_ignores_unknown_instance_type():
    cloud = cloud_with_instance(
        instance_type="ecs.exotic.weird",
        metrics=make_metrics("i-1", avg_cpu_pct=3.0, max_cpu_pct=15.0),
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_ignores_short_metrics_window():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", window_days=3, avg_cpu_pct=3.0, max_cpu_pct=15.0)
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []


def test_window_boundary_seven_days_is_accepted():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", window_days=7, avg_cpu_pct=3.0, max_cpu_pct=15.0)
    )
    assert len(EcsOverprovisionedDetector().detect(cloud)) == 1


def test_window_boundary_six_days_is_rejected():
    cloud = cloud_with_instance(
        metrics=make_metrics("i-1", window_days=6, avg_cpu_pct=3.0, max_cpu_pct=15.0)
    )
    assert EcsOverprovisionedDetector().detect(cloud) == []
