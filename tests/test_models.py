from steward.models import (
    ActionSpec,
    ActionType,
    ExecutionRecord,
    ExecutionStatus,
    Plan,
    ResourceType,
    RunResult,
)
from steward.testing import make_finding, make_planned, make_resource


def test_make_resource_factory_defaults():
    res = make_resource("i-1")
    assert res.id == "i-1"
    assert res.type is ResourceType.ECS_INSTANCE
    assert res.tags == {}
    assert res.status == "running"


def test_plan_totals_savings():
    a1 = make_planned(make_finding(make_resource("d-1"), saving=40.0))
    a2 = make_planned(make_finding(make_resource("d-2"), saving=2.5))
    plan = Plan(actions=(a1, a2))
    assert plan.total_monthly_saving_usd == 42.5


def test_planned_action_exposes_spec_shortcuts():
    finding = make_finding(
        make_resource("d-1"),
        saving=10.0,
        action_type=ActionType.DELETE_DISK,
    )
    planned = make_planned(finding, blast=2)
    assert planned.action == ActionSpec(ActionType.DELETE_DISK, "d-1", {})
    assert planned.monthly_saving_usd == 10.0
    assert planned.blast_radius == 2


def test_run_result_counts_only_executed_savings():
    executed = ExecutionRecord(
        make_planned(make_finding(make_resource("d-1"), saving=100.0)),
        ExecutionStatus.EXECUTED,
    )
    dry = ExecutionRecord(
        make_planned(make_finding(make_resource("d-2"), saving=50.0)),
        ExecutionStatus.DRY_RUN,
    )
    result = RunResult(records=(executed, dry))
    assert result.executed_saving_usd == 100.0


def test_finding_source_defaults_to_detector():
    finding = make_finding(make_resource("d-1"))
    assert finding.source == "detector"
    llm = make_finding(make_resource("d-2"), source="llm")
    assert llm.source == "llm"


def test_resource_cost_source_defaults_to_exact():
    assert make_resource("d-1").cost_source == "exact"
    assert make_resource("d-2", cost_source="estimated").cost_source == "estimated"
