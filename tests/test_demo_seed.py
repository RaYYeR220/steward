from steward.demo_seed import seed_demo
from steward.detectors import run_detectors


def test_seed_contains_known_resource_mix():
    cloud = seed_demo()
    resources = {r.id for r in cloud.list_resources()}
    assert "i-prod-web" in resources  # healthy, must never be flagged
    assert "i-staging-app" in resources
    assert "oss-archives" in resources
    assert len(resources) == 11


def test_detectors_find_exactly_the_planted_waste():
    cloud = seed_demo()
    findings = run_detectors(cloud)
    by_kind = {}
    for f in findings:
        by_kind.setdefault(f.kind, []).append(f.resource.id)
    assert sorted(by_kind["ecs_overprovisioned"]) == ["i-prod-batch", "i-staging-app"]
    assert by_kind["idle_eip"] == ["eip-orphan"]
    assert sorted(by_kind["unattached_disk"]) == ["d-orphan-1", "d-orphan-2"]
    assert sorted(by_kind["old_snapshot"]) == ["snap-old-1", "snap-old-2"]
    assert by_kind["oss_cold_bucket"] == ["oss-archives"]


def test_healthy_resources_are_never_flagged():
    cloud = seed_demo()
    flagged = {f.resource.id for f in run_detectors(cloud)}
    assert "i-prod-web" not in flagged
    assert "d-prod-web-root" not in flagged
    assert "eip-prod" not in flagged


def test_total_planted_savings():
    cloud = seed_demo()
    findings = run_detectors(cloud)
    assert round(sum(f.monthly_saving_usd for f in findings), 2) == 561.5
