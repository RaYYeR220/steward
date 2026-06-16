from steward.providers.alibaba.metrics import aggregate_cpu


def test_aggregate_cpu_avg_and_max():
    datapoints = [
        {"timestamp": 1, "Average": 2.0, "Maximum": 10.0},
        {"timestamp": 2, "Average": 4.0, "Maximum": 30.0},
        {"timestamp": 3, "Average": 6.0, "Maximum": 20.0},
    ]
    m = aggregate_cpu(datapoints, window_days=14, resource_id="i-1")
    assert m.resource_id == "i-1"
    assert m.window_days == 14
    assert m.avg_cpu_pct == 4.0  # mean of averages
    assert m.max_cpu_pct == 30.0  # max of maxima


def test_aggregate_cpu_empty_yields_none():
    m = aggregate_cpu([], window_days=14, resource_id="i-1")
    assert m.avg_cpu_pct is None
    assert m.max_cpu_pct is None
    assert m.window_days == 14


def test_aggregate_cpu_ignores_missing_fields():
    datapoints = [{"timestamp": 1, "Average": 5.0}, {"timestamp": 2, "Maximum": 9.0}]
    m = aggregate_cpu(datapoints, window_days=7, resource_id="i-2")
    assert m.avg_cpu_pct == 5.0
    assert m.max_cpu_pct == 9.0
