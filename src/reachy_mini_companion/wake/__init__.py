"""Wake word detection with pluggable backends."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reachy_mini_companion.config import WakeConfig
    from reachy_mini_companion.wake.base import BaseWakeWordDetector

logger = logging.getLogger(__name__)


def create_wake_detector(config: WakeConfig) -> BaseWakeWordDetector:
    """Create a wake word detector based on config backend setting.

    Args:
        config: Wake word configuration.

    Returns:
        A wake word detector instance (model not yet loaded).

    Raises:
        ImportError: If the required backend package is not installed.
        ValueError: If the backend is unknown.
    """
    backend = config.backend.lower()

    if backend == "edge_impulse":
        from reachy_mini_companion.wake.edge_impulse import EdgeImpulseDetector

        return EdgeImpulseDetector(
            model_path=config.custom_model_path,
            threshold=config.threshold,
            refractory_sec=config.refractory_sec,
        )

    elif backend == "openwakeword":
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector

        return OpenWakeWordDetector(
            model_name=config.model,
            custom_model_path=config.custom_model_path,
            threshold=config.threshold,
            refractory_sec=config.refractory_sec,
        )

    else:
        raise ValueError(
            f"Unknown wake word backend: '{backend}'. "
            f"Use 'edge_impulse' or 'openwakeword'."
        )
