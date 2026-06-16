from steward.detectors.eip import IdleEipDetector
from steward.models import ActionType, ResourceType
from steward.providers.mock import MockCloud
from steward.testing import make_resource


def test_flags_unattached_eip():
    cloud = MockCloud()
    cloud.add(
        make_resource("eip-1", ResourceType.EIP, status="available", monthly_cost_usd=9.0)
    )
    findings = IdleEipDetector().detect(cloud)
    assert len(findings) == 1
    assert findings[0].kind == "idle_eip"
    assert findings[0].action.type is ActionType.RELEASE_EIP
    assert findings[0].monthly_saving_usd == 9.0
    assert "not attached" in findings[0].evidence


def test_flags_eip_attached_to_stopped_instance():
    cloud = MockCloud()
    cloud.add(make_resource("i-1", status="stopped"))
    cloud.add(
        make_resource("eip-1", ResourceType.EIP, status="in_use", attached_to="i-1")
    )
    findings = IdleEipDetector().detect(cloud)
    assert len(findings) == 1
    assert "stopped instance i-1" in findings[0].evidence


def test_ignores_eip_attached_to_running_instance():
    cloud = MockCloud()
    cloud.add(make_resource("i-1", status="running"))
    cloud.add(
        make_resource("eip-1", ResourceType.EIP, status="in_use", attached_to="i-1")
    )
    assert IdleEipDetector().detect(cloud) == []


def test_ignores_non_eip_resources():
    cloud = MockCloud()
    cloud.add(make_resource("i-1", status="stopped"))
    assert IdleEipDetector().detect(cloud) == []


def test_flags_eip_with_stale_attachment_reference():
    cloud = MockCloud()
    cloud.add(
        make_resource("eip-1", ResourceType.EIP, status="in_use", attached_to="i-gone")
    )
    findings = IdleEipDetector().detect(cloud)
    assert len(findings) == 1
    assert "'i-gone'" in findings[0].evidence
    assert "no longer exists" in findings[0].evidence
