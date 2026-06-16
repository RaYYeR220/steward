from steward.providers.alibaba.cost import PRICE_MAP, CostSourcer


class FakeBss:
    def __init__(self, instance_amounts: dict[str, float]):
        self._amounts = instance_amounts

    def monthly_instance_costs(self, billing_cycle: str) -> dict[str, float]:
        return dict(self._amounts)


def test_billed_when_bill_has_the_instance():
    sourcer = CostSourcer(FakeBss({"i-1": 42.0}), billing_cycle="2026-06")
    cost, source = sourcer.monthly_cost("ecs_instance", "i-1", "ecs.g7.large")
    assert (cost, source) == (42.0, "billed")


def test_static_when_bill_empty_and_no_estimator():
    sourcer = CostSourcer(FakeBss({}), billing_cycle="2026-06")
    cost, source = sourcer.monthly_cost("ecs_instance", "i-9", "ecs.g7.large")
    assert source == "static"
    assert cost == PRICE_MAP["ecs.g7.large"]


def test_static_fallback_for_unknown_instance_type():
    sourcer = CostSourcer(FakeBss({}), billing_cycle="2026-06")
    cost, source = sourcer.monthly_cost("ecs_instance", "i-x", "ecs.unknown.huge")
    assert source == "static"
    assert cost == PRICE_MAP["_ecs_default"]


def test_static_per_kind_for_non_instances():
    sourcer = CostSourcer(FakeBss({}), billing_cycle="2026-06")
    assert sourcer.monthly_cost("eip", "eip-1", None) == (PRICE_MAP["eip"], "static")
    assert sourcer.monthly_cost("oss_bucket", "b-1", None) == (
        PRICE_MAP["oss_bucket"],
        "static",
    )


def test_estimated_tier_used_when_estimator_supplied():
    def estimator(kind, instance_type):
        return 7.5 if instance_type == "ecs.g7.large" else None

    sourcer = CostSourcer(FakeBss({}), billing_cycle="2026-06", estimator=estimator)
    assert sourcer.monthly_cost("ecs_instance", "i-1", "ecs.g7.large") == (7.5, "estimated")
    # estimator returning None falls through to static
    cost, source = sourcer.monthly_cost("ecs_instance", "i-2", "ecs.unknown.huge")
    assert source == "static"


def test_bill_is_fetched_once_and_cached():
    calls = {"n": 0}

    class CountingBss(FakeBss):
        def monthly_instance_costs(self, billing_cycle):
            calls["n"] += 1
            return super().monthly_instance_costs(billing_cycle)

    sourcer = CostSourcer(CountingBss({"i-1": 10.0}), billing_cycle="2026-06")
    sourcer.monthly_cost("ecs_instance", "i-1", "ecs.g7.large")
    sourcer.monthly_cost("ecs_instance", "i-1", "ecs.g7.large")
    assert calls["n"] == 1


def test_bill_fetch_exception_falls_back_to_static(caplog):
    import logging

    class ExplodingBss:
        def monthly_instance_costs(self, billing_cycle):
            raise RuntimeError("BSS auth failed")

    sourcer = CostSourcer(ExplodingBss(), billing_cycle="2026-06")
    with caplog.at_level(logging.WARNING):
        cost, source = sourcer.monthly_cost("ecs_instance", "i-1", "ecs.g7.large")
    assert source == "static"
    assert cost == PRICE_MAP["ecs.g7.large"]
    assert any("BSS bill fetch failed" in r.message for r in caplog.records)
