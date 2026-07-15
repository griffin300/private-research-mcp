from __future__ import annotations

from datetime import UTC, datetime


def freshness_score(published_at: datetime | None, *, time_sensitive: bool) -> float:
    if published_at is None:
        return 0.35 if time_sensitive else 0.5
    value = published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(UTC) - value).days)
    half_life = 180 if time_sensitive else 1460
    return round(1 / (1 + age_days / half_life), 4)
