"""Hybrid per-resource monthly cost: billed (real spend) -> estimated -> static.

The fresh free-tier account has no real spend, so DescribeInstanceBill returns
empty and we fall back. The ``estimated`` tier is pluggable (a live price-API
estimator) but defaults to off; ``static`` (a public-price map) is the reliable
floor. Every result is tagged with its source so the report can be honest.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol

_log = logging.getLogger(__name__)

# Conservative public pay-as-you-go monthly approximations (USD). Labelled
# "static" wherever used so they are never mistaken for real billing.
PRICE_MAP: dict[str, float] = {
    "ecs.g7.large": 70.0,
    "ecs.g7.xlarge": 140.0,
    "ecs.g7.2xlarge": 280.0,
    "ecs.g7.4xlarge": 560.0,
    "ecs.c7.large": 60.0,
    "ecs.c7.xlarge": 120.0,
    "ecs.c7.2xlarge": 240.0,
    "ecs.c7.4xlarge": 480.0,
    "_ecs_default": 100.0,
    "eip": 9.0,
    "disk": 20.0,
    "snapshot": 6.0,
    "oss_bucket": 25.0,
}

# An estimator maps (resource_kind, instance_type) -> monthly USD, or None.
Estimator = Callable[[str, str | None], float | None]


class BillSource(Protocol):
    def monthly_instance_costs(self, billing_cycle: str) -> dict[str, float]: ...


class CostSourcer:
    def __init__(
        self,
        bill_source: BillSource,
        *,
        billing_cycle: str,
        estimator: Estimator | None = None,
    ) -> None:
        self._bill_source = bill_source
        self._billing_cycle = billing_cycle
        self._estimator = estimator
        self._bill: dict[str, float] | None = None

    def _billed(self, instance_id: str) -> float | None:
        if self._bill is None:
            try:
                self._bill = self._bill_source.monthly_instance_costs(self._billing_cycle)
            except Exception as exc:  # noqa: BLE001 — a failed bill must not break a scan
                _log.warning("BSS bill fetch failed, falling back to static pricing: %s", exc)
                self._bill = {}
        amount = self._bill.get(instance_id)
        # Spec: "empty/zero -> next tier". On the free-tier sandbox real spend is
        # $0, so a $0/absent bill entry deliberately falls through to estimated/
        # static pricing — otherwise every resource would show $0 and the agent
        # would have nothing to optimize.
        return amount if amount else None

    def _static(self, kind: str, instance_type: str | None) -> float:
        if kind == "ecs_instance":
            return PRICE_MAP.get(instance_type or "", PRICE_MAP["_ecs_default"])
        return PRICE_MAP.get(kind, PRICE_MAP["_ecs_default"])

    def monthly_cost(
        self, kind: str, instance_id: str, instance_type: str | None
    ) -> tuple[float, str]:
        billed = self._billed(instance_id)
        if billed is not None:
            return billed, "billed"
        if self._estimator is not None:
            estimate = self._estimator(kind, instance_type)
            if estimate is not None:
                return float(estimate), "estimated"
        return self._static(kind, instance_type), "static"
