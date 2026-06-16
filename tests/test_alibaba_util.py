from datetime import datetime, timezone

from steward.providers.alibaba.util import age_days_from


FIXED_NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)


def test_age_days_from_iso_z():
    assert age_days_from("2026-06-01T00:00:00Z", now=FIXED_NOW) == 14


def test_age_days_from_iso_offset():
    assert age_days_from("2026-05-16T00:00:00+00:00", now=FIXED_NOW) == 30


def test_age_days_from_date_only():
    assert age_days_from("2026-06-10", now=FIXED_NOW) == 5


def test_age_days_from_blank_is_zero():
    assert age_days_from("", now=FIXED_NOW) == 0
    assert age_days_from(None, now=FIXED_NOW) == 0


def test_age_days_never_negative():
    assert age_days_from("2026-07-01T00:00:00Z", now=FIXED_NOW) == 0
