"""Pure helpers shared by the Alibaba service mappers."""
from __future__ import annotations

from datetime import datetime, timezone


def age_days_from(created: str | None, *, now: datetime | None = None) -> int:
    """Whole days between an ISO-8601 creation timestamp and ``now`` (UTC).

    Tolerates ``Z``, explicit offsets, and date-only strings. Blank/unparseable
    input or a future date yields 0 (never negative).
    """
    if not created:
        return 0
    now = now or datetime.now(timezone.utc)
    text = created.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.fromisoformat(text + "T00:00:00+00:00")
        except ValueError:
            return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta_days = (now - moment).days
    return max(delta_days, 0)
