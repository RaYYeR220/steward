from steward.executor import is_reversible, run
from steward.models import (
    ActionType,
    ExecutionStatus,
    GateDecision,
    ResourceType,
)
from steward.providers.base import CloudError
from steward.providers.mock import MockCloud
from steward.testing import make_finding, make_planned, make_resource


def allowed(planned):
    return GateDecision(action=planned, allowed=True)


def blocked(planned, *reasons):
    return GateDecision(action=planned, allowed=False, reasons=tuple(reasons))


def resize_action(cloud, *, instance_id="i-1", status="running"):
    instance = make_resource(
        instance_id, spec={"instance_type": "ecs.g7.2xlarge"}, status=status
    )
    cloud.add(instance)
    finding = make_finding(
        instance,
        action_type=ActionType.RESIZE_ECS,
        params={"target_instance_type": "ecs.g7.xlarge"},
        saving=150.0,
    )
    return make_planned(finding, blast=4)


def disk_delete_action(cloud, *, disk_id="d-1", attached_to=None):
    disk = make_resource(
        disk_id,
        ResourceType.DISK,
        status="available",
        spec={"size_gb": 200},
        attached_to=attached_to,
        age_days=90,
        monthly_cost_usd=44.0,
    )
    cloud.add(disk)
    finding = make_finding(disk, action_type=ActionType.DELETE_DISK, saving=44.0)
    return make_planned(finding, blast=2)


def eip_release_action(cloud, *, eip_id="eip-1", attached_to=None):
    eip = make_resource(
        eip_id, ResourceType.EIP, status="available", attached_to=attached_to
    )
    cloud.add(eip)
    finding = make_finding(eip, action_type=ActionType.RELEASE_EIP, saving=9.0)
    return make_planned(finding, blast=1)


def test_reversibility_map():
    assert is_reversible(ActionType.RESIZE_ECS) is True
    assert is_reversible(ActionType.DELETE_DISK) is True  # via safety snapshot
    assert is_reversible(ActionType.CHANGE_OSS_CLASS) is True
    assert is_reversible(ActionType.RELEASE_EIP) is False
    assert is_reversible(ActionType.DELETE_SNAPSHOT) is False


def test_dry_run_changes_nothing():
    cloud = MockCloud()
    planned = resize_action(cloud)
    result = run(cloud, [allowed(planned)], dry_run=True)
    assert result.records[0].status is ExecutionStatus.DRY_RUN
    assert cloud.get_resource("i-1").spec["instance_type"] == "ecs.g7.2xlarge"
    assert result.executed_saving_usd == 0.0


def test_execute_applies_action_and_records_before_state():
    cloud = MockCloud()
    planned = resize_action(cloud)
    result = run(cloud, [allowed(planned)], dry_run=False)
    record = result.records[0]
    assert record.status is ExecutionStatus.EXECUTED
    assert record.before_state["spec"]["instance_type"] == "ecs.g7.2xlarge"
    assert cloud.get_resource("i-1").spec["instance_type"] == "ecs.g7.xlarge"
    assert result.executed_saving_usd == 150.0


def test_blocked_actions_are_recorded_not_executed():
    cloud = MockCloud()
    planned = resize_action(cloud)
    result = run(cloud, [blocked(planned, "protected by tag env=production")], dry_run=False)
    assert result.records[0].status is ExecutionStatus.BLOCKED
    assert "protected" in result.records[0].reasons[0]
    assert cloud.get_resource("i-1").spec["instance_type"] == "ecs.g7.2xlarge"


def test_failed_action_halts_batch():
    cloud = MockCloud()
    first = disk_delete_action(cloud, disk_id="d-1")
    second = disk_delete_action(cloud, disk_id="d-2")
    cloud.fail_on.add("d-1")
    result = run(cloud, [allowed(first), allowed(second)], dry_run=False)
    assert result.records[0].status is ExecutionStatus.FAILED
    assert result.records[1].status is ExecutionStatus.NOT_REACHED
    assert cloud.get_resource("d-2") is not None  # untouched


def test_unhealthy_verification_rolls_back_resize():
    cloud = MockCloud()
    planned = resize_action(cloud)
    cloud.unhealthy.add("i-1")
    result = run(cloud, [allowed(planned)], dry_run=False)
    record = result.records[0]
    assert record.status is ExecutionStatus.ROLLED_BACK
    assert "health check failed" in record.error
    # the resize was undone
    assert cloud.get_resource("i-1").spec["instance_type"] == "ecs.g7.2xlarge"
    assert result.executed_saving_usd == 0.0


def test_disk_delete_creates_safety_snapshot_and_restores_on_failure():
    cloud = MockCloud()
    planned = disk_delete_action(cloud, attached_to="i-parent")
    cloud.add(make_resource("i-parent", status="running"))
    cloud.unhealthy.add("i-parent")
    result = run(cloud, [allowed(planned)], dry_run=False)
    assert result.records[0].status is ExecutionStatus.ROLLED_BACK
    assert cloud.get_resource("d-1") is not None  # restored from safety snapshot


def test_irreversible_action_failure_is_reported_not_rolled_back():
    cloud = MockCloud()
    cloud.add(make_resource("i-stopped", status="stopped"))
    planned = eip_release_action(cloud, attached_to="i-stopped")
    cloud.unhealthy.add("i-stopped")
    result = run(cloud, [allowed(planned)], dry_run=False)
    record = result.records[0]
    assert record.status is ExecutionStatus.FAILED
    assert "irreversible" in record.error


def test_unattached_eip_release_skips_health_check():
    cloud = MockCloud()
    planned = eip_release_action(cloud, attached_to=None)
    result = run(cloud, [allowed(planned)], dry_run=False)
    assert result.records[0].status is ExecutionStatus.EXECUTED
    assert cloud.get_resource("eip-1") is None


def test_rollback_failure_is_recorded_not_raised():
    cloud = MockCloud()
    planned = resize_action(cloud)
    cloud.unhealthy.add("i-1")
    # First resize (the action) succeeds; second resize (the rollback) fails.
    original_resize = cloud.resize_instance
    calls = {"n": 0}

    def flaky_resize(instance_id, target_instance_type):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise CloudError("resize API down")
        original_resize(instance_id, target_instance_type)

    cloud.resize_instance = flaky_resize
    result = run(cloud, [allowed(planned)], dry_run=False)
    record = result.records[0]
    assert record.status is ExecutionStatus.ROLLBACK_FAILED
    assert "MANUAL INTERVENTION" in record.error
    assert record.before_state is not None


def test_failed_disk_delete_cleans_up_safety_snapshot():
    class DeleteAlwaysFails(MockCloud):
        def delete_disk(self, disk_id):
            raise CloudError(f"delete API down for {disk_id}")

    cloud = DeleteAlwaysFails()
    planned = disk_delete_action(cloud)
    result = run(cloud, [allowed(planned)], dry_run=False)
    assert result.records[0].status is ExecutionStatus.FAILED
    assert cloud.get_resource("d-1") is not None  # disk untouched
    leaked = [r for r in cloud.list_resources() if r.id.startswith("snap-rollback-")]
    assert leaked == []  # safety snapshot was cleaned up
