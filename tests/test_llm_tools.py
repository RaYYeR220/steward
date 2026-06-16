import json

from steward.demo_seed import seed_demo
from steward.detectors import run_detectors
from steward.llm.client import ToolCall
from steward.llm.tools import TOOL_SCHEMAS, ToolSession
from steward.models import ActionType


def make_session():
    cloud = seed_demo()
    findings = run_detectors(cloud)
    return ToolSession(cloud, findings), cloud, findings


def call(name, **args):
    return ToolCall(id="t1", name=name, arguments=json.dumps(args))


def valid_proposal_args(**overrides):
    args = {
        "action_type": "release_eip",
        "resource_id": "eip-prod",
        "evidence": "EIP sits behind a load balancer and is never the entry point",
        "estimated_monthly_saving_usd": 3.0,
    }
    args.update(overrides)
    return args


def test_schemas_cover_all_five_tools():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {
        "list_resources",
        "get_metrics",
        "get_findings",
        "propose_action",
        "finish_investigation",
    }


def test_list_resources_returns_full_inventory():
    session, _, _ = make_session()
    result = json.loads(session.dispatch(call("list_resources")))
    assert len(result["resources"]) == 11
    by_id = {r["id"]: r for r in result["resources"]}
    assert by_id["i-staging-app"]["spec"]["instance_type"] == "ecs.g7.4xlarge"
    assert by_id["i-prod-web"]["tags"] == {"env": "production"}


def test_get_metrics_round_trip_and_null():
    session, _, _ = make_session()
    got = json.loads(session.dispatch(call("get_metrics", resource_id="i-staging-app")))
    assert got["metrics"]["avg_cpu_pct"] == 3.2
    missing = json.loads(session.dispatch(call("get_metrics", resource_id="d-orphan-1")))
    assert missing["metrics"] is None


def test_get_findings_exposes_detector_results():
    session, _, findings = make_session()
    got = json.loads(session.dispatch(call("get_findings")))
    assert len(got["findings"]) == len(findings)
    kinds = {f["kind"] for f in got["findings"]}
    assert "ecs_overprovisioned" in kinds


def test_propose_action_accepts_valid_proposal():
    session, _, _ = make_session()
    result = json.loads(session.dispatch(call("propose_action", **valid_proposal_args())))
    assert result == {"accepted": True}
    assert len(session.proposals) == 1
    finding = session.proposals[0]
    assert finding.source == "llm"
    assert finding.kind == "llm_release_eip"
    assert finding.action.type is ActionType.RELEASE_EIP
    assert finding.monthly_saving_usd == 3.0


def test_propose_action_rejects_unknown_action_type():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(call("propose_action", **valid_proposal_args(action_type="terminate_everything")))
    )
    assert result["accepted"] is False
    assert "unknown action_type" in result["error"]


def test_propose_action_rejects_missing_resource():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(call("propose_action", **valid_proposal_args(resource_id="i-ghost")))
    )
    assert result["accepted"] is False
    assert "no such resource" in result["error"]


def test_propose_action_rejects_missing_required_param():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(
            call(
                "propose_action",
                action_type="resize_ecs",
                resource_id="i-prod-web",
                evidence="some evidence",
                estimated_monthly_saving_usd=10.0,
            )
        )
    )
    assert result["accepted"] is False
    assert "target_instance_type" in result["error"]


def test_propose_action_rejects_same_size_resize():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(
            call(
                "propose_action",
                action_type="resize_ecs",
                resource_id="i-prod-web",
                params={"target_instance_type": "ecs.g7.xlarge"},  # current type
                evidence="some evidence",
                estimated_monthly_saving_usd=10.0,
            )
        )
    )
    assert result["accepted"] is False
    assert "equals the current" in result["error"]


def test_propose_action_rejects_negative_saving():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(
            call("propose_action", **valid_proposal_args(estimated_monthly_saving_usd=-5))
        )
    )
    assert result["accepted"] is False
    assert "non-negative" in result["error"]


def test_propose_action_caps_saving_at_resource_cost():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(
            call("propose_action", **valid_proposal_args(estimated_monthly_saving_usd=999.0))
        )
    )
    assert result == {"accepted": True}
    assert session.proposals[0].monthly_saving_usd == 3.0  # eip-prod costs $3/mo


def test_propose_action_rejects_empty_evidence():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(call("propose_action", **valid_proposal_args(evidence="   ")))
    )
    assert result["accepted"] is False
    assert "evidence" in result["error"]


def test_propose_action_rejects_duplicate_of_detector_finding():
    session, _, _ = make_session()
    # the ECS detector already flags i-staging-app for resize
    result = json.loads(
        session.dispatch(
            call(
                "propose_action",
                action_type="resize_ecs",
                resource_id="i-staging-app",
                params={"target_instance_type": "ecs.g7.large"},
                evidence="idle box",
                estimated_monthly_saving_usd=100.0,
            )
        )
    )
    assert result["accepted"] is False
    assert "duplicate" in result["error"]


def test_propose_action_rejects_duplicate_of_prior_proposal():
    session, _, _ = make_session()
    first = json.loads(session.dispatch(call("propose_action", **valid_proposal_args())))
    assert first == {"accepted": True}
    second = json.loads(session.dispatch(call("propose_action", **valid_proposal_args())))
    assert second["accepted"] is False
    assert "duplicate" in second["error"]


def test_dispatch_handles_malformed_json_arguments():
    session, _, _ = make_session()
    bad = ToolCall(id="t1", name="list_resources", arguments="{not json")
    result = json.loads(session.dispatch(bad))
    assert "not valid JSON" in result["error"]


def test_dispatch_rejects_unknown_tool():
    session, _, _ = make_session()
    result = json.loads(session.dispatch(call("rm_minus_rf")))
    assert "unknown tool" in result["error"]


def test_finish_investigation_sets_state():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(call("finish_investigation", summary="Two leaks found."))
    )
    assert result == {"ok": True}
    assert session.finished is True
    assert session.summary == "Two leaks found."


def test_propose_action_rejects_nan_saving():
    session, _, _ = make_session()
    raw = ToolCall(
        id="t1",
        name="propose_action",
        arguments=(
            '{"action_type": "release_eip", "resource_id": "eip-prod", '
            '"evidence": "x", "estimated_monthly_saving_usd": NaN}'
        ),
    )
    result = json.loads(session.dispatch(raw))
    assert result["accepted"] is False
    assert "finite" in result["error"]


def test_propose_action_rejects_infinite_saving():
    session, _, _ = make_session()
    raw = ToolCall(
        id="t1",
        name="propose_action",
        arguments=(
            '{"action_type": "release_eip", "resource_id": "eip-prod", '
            '"evidence": "x", "estimated_monthly_saving_usd": Infinity}'
        ),
    )
    result = json.loads(session.dispatch(raw))
    assert result["accepted"] is False
    assert "finite" in result["error"]


def test_propose_action_rejects_non_string_evidence():
    session, _, _ = make_session()
    result = json.loads(
        session.dispatch(call("propose_action", **valid_proposal_args(evidence={"a": 1})))
    )
    assert result["accepted"] is False
    assert "evidence" in result["error"]
