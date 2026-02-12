"""Session-level cost estimation and budget tracking."""

from __future__ import annotations

import logging
import time

from reachy_mini_companion.config import AppConfig
from reachy_mini_companion.cost.db import CostDatabase

logger = logging.getLogger(__name__)

# Approximate tokens per second of audio
AUDIO_TOKENS_PER_SEC = 32  # ~32 tokens/sec for Gemini audio


class CostTracker:
    """Tracks cost per session and enforces daily budget.

    Pricing (per million tokens):
    - Input audio: $0.70
    - Output audio: $7.00
    - Input text: $0.15
    - Output text: $0.60
    """

    def __init__(self, config: AppConfig, db: CostDatabase | None = None):
        self.config = config
        self.db = db
        self._pricing = config.cost.pricing
        self._daily_budget = config.cost.daily_budget_usd

        self._session_id: int | None = None
        self._session_start: float = 0.0
        self._session_input_audio_sec: float = 0.0
        self._session_output_audio_sec: float = 0.0

    async def start_session(self) -> int | None:
        """Start a new session. Returns session ID."""
        self._session_start = time.monotonic()
        self._session_input_audio_sec = 0.0
        self._session_output_audio_sec = 0.0

        if self.db:
            self._session_id = await self.db.log_session_start()
            return self._session_id
        return None

    async def end_session(self) -> float:
        """End current session. Returns estimated cost."""
        duration = time.monotonic() - self._session_start
        cost = self.estimate_session_cost()

        if self.db and self._session_id is not None:
            await self.db.log_session_end(self._session_id, duration, cost)
            # Log token usage
            input_tokens = int(self._session_input_audio_sec * AUDIO_TOKENS_PER_SEC)
            output_tokens = int(self._session_output_audio_sec * AUDIO_TOKENS_PER_SEC)
            await self.db.log_usage(
                self._session_id,
                input_audio_tokens=input_tokens,
                output_audio_tokens=output_tokens,
                estimated_cost_usd=cost,
            )

        logger.info(f"Session ended: duration={duration:.1f}s, cost=${cost:.4f}")
        self._session_id = None
        return cost

    def add_input_audio(self, seconds: float) -> None:
        """Record input audio duration."""
        self._session_input_audio_sec += seconds

    def add_output_audio(self, seconds: float) -> None:
        """Record output audio duration."""
        self._session_output_audio_sec += seconds

    def estimate_session_cost(self) -> float:
        """Estimate cost of current session based on audio duration."""
        input_tokens = self._session_input_audio_sec * AUDIO_TOKENS_PER_SEC
        output_tokens = self._session_output_audio_sec * AUDIO_TOKENS_PER_SEC

        input_cost = (input_tokens / 1_000_000) * self._pricing.input_audio_per_million
        output_cost = (output_tokens / 1_000_000) * self._pricing.output_audio_per_million

        return input_cost + output_cost

    async def check_budget(self) -> bool:
        """Check if daily budget allows another session.

        Returns:
            True if within budget, False if budget exceeded.
        """
        if self.db:
            daily_total = await self.db.get_daily_total()
            remaining = self._daily_budget - daily_total
            if remaining <= 0:
                logger.warning(
                    f"Daily budget exceeded: ${daily_total:.4f} / ${self._daily_budget:.2f}"
                )
                return False
            logger.info(f"Budget remaining: ${remaining:.4f}")
        return True
