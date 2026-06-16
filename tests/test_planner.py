from steward.models import ActionType, ResourceType
from steward.planner import build_plan, score_blast
from steward.providers.mock import MockCloud
from steward.testing import make_finding, make_resource


def test_base_blast_scores_per_action_type():
    cloud = MockCloud()
    snap = make_resource("snap-1", ResourceType.SNAPSHOT, status="available")
    cloud.add(snap)
    finding = make_finding(snap, action_type=ActionType.DELETE_SNAPSHOT)
    score, reasons = score_blast(finding, cloud)
    assert score == 1
    assert any("base risk" in r for r in reasons)


def test_running_resource_raises_blast():
    cloud = MockCloud()
    instance = make_resource("i-1", status="running")
    cloud.add(instance)
    finding = make_finding(instance, action_type=ActionType.RESIZE_ECS)
    score, reasons = score_blast(finding, cloud)
    assert score == 4  # base 3 + running 1
    assert any("running" in r for r in reasons)


def test_dependents_raise_blast():
    cloud = MockCloud()
    instance = make_resource("i-1", status="stopped")
    cloud.add(instance)
    cloud.add(
        make_resource("d-1", ResourceType.DISK, status="in_use", attached_to="i-1")
    )
    finding = make_finding(instance, action_type=ActionType.RESIZE_ECS)
    score, reasons = score_blast(finding, cloud)
    assert score == 4  # base 3 + dependents 1
    assert any("d-1" in r for r in reasons)


def test_blast_is_capped_at_five():
    cloud = MockCloud()
    instance = make_resource("i-1", status="running")
    cloud.add(instance)
    for n in range(3):
        cloud.add(
            make_resource(
                f"d-{n}", ResourceType.DISK, status="in_use", attached_to="i-1"
            )
        )
    finding = make_finding(instance, action_type=ActionType.RESIZE_ECS)
    score, _ = score_blast(finding, cloud)
    assert score == 5


def test_build_plan_orders_safe_first_then_biggest_saving():
    cloud = MockCloud()
    snap = make_resource("snap-1", ResourceType.SNAPSHOT, status="available")
    disk_small = make_resource("d-small", ResourceType.DISK, status="available")
    disk_big = make_resource("d-big", ResourceType.DISK, status="available")
    for res in (snap, disk_small, disk_big):
        cloud.add(res)
    findings = [
        make_finding(disk_small, action_type=ActionType.DELETE_DISK, saving=5.0),
        make_finding(snap, action_type=ActionType.DELETE_SNAPSHOT, saving=1.0),
        make_finding(disk_big, action_type=ActionType.DELETE_DISK, saving=80.0),
    ]
    plan = build_plan(findings, cloud)
    ordered_ids = [a.finding.resource.id for a in plan.actions]
    # blast 1 (snapshot) first, then blast 2 disks by saving descending
    assert ordered_ids == ["snap-1", "d-big", "d-small"]
    assert plan.total_monthly_saving_usd == 86.0


def test_llm_sourced_finding_gets_blast_penalty():
    cloud = MockCloud()
    disk = make_resource("d-1", ResourceType.DISK, status="available")
    cloud.add(disk)
    finding = make_finding(disk, action_type=ActionType.DELETE_DISK, source="llm")
    score, reasons = score_blast(finding, cloud)
    assert score == 3  # base 2 + llm 1
    assert any("proposed by LLM" in r for r in reasons)
