"""Voice Activity Detection using RMS-based silence detection."""

from __future__ import annotations

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)


class SilenceDetector:
    """Detects sustained silence in an audio stream using RMS energy.

    Used during ACTIVE state to determine when the user has stopped talking.
    """

    def __init__(
        self,
        timeout_sec: float = 15.0,
        rms_threshold: int = 200,
    ):
        self.timeout_sec = timeout_sec
        self.rms_threshold = rms_threshold
        self._last_speech_time: float | None = None

    def process(self, audio: np.ndarray, current_time: float | None = None) -> bool:
        """Process audio and check if silence timeout has been exceeded.

        Args:
            audio: Audio samples (int16 mono).
            current_time: Override for current time (for testing).

        Returns:
            True if silence has lasted longer than timeout_sec.
        """
        now = current_time if current_time is not None else time.monotonic()

        if self._last_speech_time is None:
            self._last_speech_time = now

        # Calculate RMS energy
        if audio.dtype == np.float32:
            rms = np.sqrt(np.mean(audio ** 2)) * 32767
        else:
            rms = np.sqrt(np.mean(audio.astype(np.float64) ** 2))

        if rms >= self.rms_threshold:
            self._last_speech_time = now
            return False

        silence_duration = now - self._last_speech_time
        if silence_duration >= self.timeout_sec:
            logger.info(f"Silence timeout reached ({silence_duration:.1f}s)")
            return True

        return False

    def reset(self) -> None:
        """Reset the silence timer."""
        self._last_speech_time = None
