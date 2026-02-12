"""Tests for cost tracking system."""

import pytest

from reachy_mini_companion.config import AppConfig
from reachy_mini_companion.cost.db import CostDatabase
from reachy_mini_companion.cost.tracker import CostTracker


@pytest.fixture
async def db(tmp_path):
    """Create a test database."""
    db = CostDatabase(str(tmp_path / "test_cost.db"))
    await db.initialize()
    yield db
    await db.close()


async def test_db_initialize(db):
    """Database should initialize without errors."""
    assert db._db is not None


async def test_log_session(db):
    """Should log session start and end."""
    session_id = await db.log_session_start()
    assert session_id is not None
    assert session_id > 0

    await db.log_session_end(session_id, duration_sec=10.5, total_cost_usd=0.001)

    # Verify via daily total
    daily = await db.get_daily_total()
    assert daily >= 0.001


async def test_log_usage(db):
    """Should log token usage."""
    session_id = await db.log_session_start()
    await db.log_usage(
        session_id,
        input_audio_tokens=1000,
        output_audio_tokens=500,
        estimated_cost_usd=0.0042,
    )
    # Should not raise


async def test_daily_total_empty(db):
    """Empty database should return 0."""
    total = await db.get_daily_total()
    assert total == 0.0


async def test_daily_total_specific_date(db):
    """Should return 0 for dates with no sessions."""
    total = await db.get_daily_total("2020-01-01")
    assert total == 0.0


class TestCostTracker:
    async def test_estimate_cost(self, tmp_path):
        config = AppConfig()
        tracker = CostTracker(config)
        await tracker.start_session()
        tracker.add_input_audio(60.0)  # 1 minute of input audio
        tracker.add_output_audio(30.0)  # 30 seconds of output audio

        cost = tracker.estimate_session_cost()
        assert cost > 0
        assert cost < 1.0  # Sanity check

    async def test_check_budget_within(self, tmp_path):
        config = AppConfig()
        db = CostDatabase(str(tmp_path / "budget_test.db"))
        await db.initialize()
        tracker = CostTracker(config, db)

        within = await tracker.check_budget()
        assert within is True
        await db.close()

    async def test_check_budget_exceeded(self, tmp_path):
        config = AppConfig()
        config.cost.daily_budget_usd = 0.001  # Very low budget

        db = CostDatabase(str(tmp_path / "budget_test.db"))
        await db.initialize()

        # Log a session that exceeds budget
        session_id = await db.log_session_start()
        await db.log_session_end(session_id, duration_sec=100, total_cost_usd=0.01)

        tracker = CostTracker(config, db)
        within = await tracker.check_budget()
        assert within is False
        await db.close()

    async def test_session_lifecycle(self, tmp_path):
        config = AppConfig()
        db = CostDatabase(str(tmp_path / "lifecycle.db"))
        await db.initialize()
        tracker = CostTracker(config, db)

        await tracker.start_session()
        tracker.add_input_audio(10.0)
        cost = await tracker.end_session()
        assert cost >= 0

        daily = await db.get_daily_total()
        assert daily >= 0
        await db.close()
