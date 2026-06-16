from steward.models import ActionType, Plan, ResourceType
from steward.policy import Policy, gate
from steward.testing import make_finding, make_planned, make_resource


def plan_of(*planned):
    return Plan(actions=tuple(planned))


def disk_action(disk_id="d-1", *, saving=10.0, blast=2, tags=None):
    disk = make_resource(
        disk_id, ResourceType.DISK, status="available", tags=tags or {}, age_days=90
    )
    return make_planned(
        make_finding(disk, action_type=ActionType.DELETE_DISK, saving=saving),
        blast=blast,
    )


def test_clean_action_is_allowed():
    decisions = gate(plan_of(disk_action()), Policy())
    assert decisions[0].allowed is True
    assert decisions[0].reasons == ()


def test_protected_tag_blocks():
    action = disk_action(tags={"env": "production"})
    decisions = gate(plan_of(action), Policy())
    assert decisions[0].allowed is False
    assert "protected by tag env=production" in decisions[0].reasons


def test_blast_radius_above_policy_max_blocks():
    action = disk_action(blast=4)
    decisions = gate(plan_of(action), Policy(max_blast_radius=3))
    assert decisions[0].allowed is False
    assert any("blast radius 4" in r for r in decisions[0].reasons)


def test_irreversible_blocked_unless_opted_in():
    eip = make_resource("eip-1", ResourceType.EIP, status="available")
    action = make_planned(
        make_finding(eip, action_type=ActionType.RELEASE_EIP, saving=9.0), blast=1
    )
    blocked = gate(plan_of(action), Policy())
    assert blocked[0].allowed is False
    assert any("irreversible" in r for r in blocked[0].reasons)
    allowed = gate(plan_of(action), Policy(allow_irreversible=True))
    assert allowed[0].allowed is True


def test_max_actions_per_run():
    actions = [disk_action(f"d-{n}") for n in range(3)]
    decisions = gate(plan_of(*actions), Policy(max_actions=2))
    assert [d.allowed for d in decisions] == [True, True, False]
    assert any("max 2 actions" in r for r in decisions[2].reasons)


def test_monthly_change_budget_cap():
    actions = [
        disk_action("d-1", saving=300.0),
        disk_action("d-2", saving=250.0),
    ]
    decisions = gate(plan_of(*actions), Policy(max_monthly_change_usd=400.0))
    assert decisions[0].allowed is True
    assert decisions[1].allowed is False
    assert any("budget" in r for r in decisions[1].reasons)


def test_multiple_reasons_accumulate():
    action = disk_action(tags={"env": "production"}, blast=5)
    decisions = gate(plan_of(action), Policy(max_blast_radius=2))
    assert len(decisions[0].reasons) == 2


def test_block_llm_proposed_blocks_only_llm_findings():
    detector_action = disk_action("d-det")
    llm_disk = make_resource("d-llm", ResourceType.DISK, status="available", age_days=90)
    llm_action = make_planned(
        make_finding(llm_disk, action_type=ActionType.DELETE_DISK, source="llm"),
        blast=2,
    )
    decisions = gate(
        plan_of(detector_action, llm_action), Policy(block_llm_proposed=True)
    )
    assert decisions[0].allowed is True
    assert decisions[1].allowed is False
    assert any("interactive approval" in r for r in decisions[1].reasons)


def test_llm_findings_allowed_when_not_blocked():
    llm_disk = make_resource("d-llm", ResourceType.DISK, status="available", age_days=90)
    llm_action = make_planned(
        make_finding(llm_disk, action_type=ActionType.DELETE_DISK, source="llm"),
        blast=2,
    )
    decisions = gate(plan_of(llm_action), Policy())
    assert decisions[0].allowed is True
