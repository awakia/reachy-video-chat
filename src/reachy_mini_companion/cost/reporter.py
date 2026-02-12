"""Cost reporting for dashboard (Phase 2)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from reachy_mini_companion.cost.db import CostDatabase

logger = logging.getLogger(__name__)


class CostReporter:
    """Generates cost summaries for the web dashboard."""

    def __init__(self, db: CostDatabase):
        self.db = db

    async def daily_summary(self, date_str: str | None = None) -> dict:
        """Get summary for a single day."""
        total = await self.db.get_daily_total(date_str)
        return {
            "date": date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_cost_usd": total,
        }

    async def weekly_summary(self) -> list[dict]:
        """Get daily summaries for the past 7 days."""
        results = []
        today = datetime.now(timezone.utc).date()
        for i in range(7):
            day = today - timedelta(days=i)
            date_str = day.isoformat()
            total = await self.db.get_daily_total(date_str)
            results.append({"date": date_str, "total_cost_usd": total})
        return results
