from steward.demo_seed import seed_demo
from steward.policy import Policy
from steward.snapshot import (
    plan_snapshot,
    run_snapshot,
    scan_snapshot,
)
from steward.executor import run as execute_run
from steward.planner import build_plan
from steward.detectors import run_detectors
from steward.policy import gate


def test_scan_snapshot_shape_and_numbers():
    snap = scan_snapshot(seed_demo())
    assert snap["total_monthly_usd"] == 1278.0
    assert snap["potential_saving_usd"] == 561.5
    assert len(snap["resources"]) == 11
    assert {f["resource_id"] for f in snap["findings"]}  # non-empty
    res = next(r for r in snap["resources"] if r["id"] == "i-staging-app")
    assert res["type"] == "ecs_instance"
    assert res["cost_source"] == "exact"
    assert snap["warnings"] == []


def test_plan_snapshot_allowed_and_blocked():
    snap = plan_snapshot(seed_demo(), Policy(max_blast_radius=4, allow_irreversible=True))
    blocked = [d for d in snap["decisions"] if not d["allowed"]]
    assert any(d["resource_id"] == "i-prod-batch" for d in blocked)
    assert snap["allowed_saving_usd"] == 421.5
    assert snap["blocked_saving_usd"] == 140.0
    one = next(d for d in snap["decisions"] if d["resource_id"] == "i-prod-batch")
    assert any("env=production" in r for r in one["reasons"])
    assert one["blast_radius"] >= 1


def test_run_snapshot_before_after():
    provider = seed_demo()
    findings = run_detectors(provider)
    plan = build_plan(findings, provider)
    decisions = gate(plan, Policy(max_blast_radius=4, allow_irreversible=True))
    result = execute_run(provider, decisions, dry_run=False)
    snap = run_snapshot(result, dry_run=False, total_monthly_usd=1278.0, narrative="hi")
    assert snap["mode"] == "execute"
    assert snap["applied_saving_usd"] == 421.5
    assert snap["before_usd"] == 1278.0
    assert snap["after_usd"] == 1278.0 - 421.5
    assert snap["narrative"] == "hi"
    statuses = {r["status"] for r in snap["records"]}
    assert "executed" in statuses
