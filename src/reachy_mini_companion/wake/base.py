"""Base class for wake word detectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class BaseWakeWordDetector(ABC):
    """Common interface for wake word detection backends."""

    @abstractmethod
    def load_model(self) -> None:
        """Load the wake word model."""

    @abstractmethod
    def process_audio(self, audio: np.ndarray) -> bool:
        """Process audio chunk and return True if wake word detected."""

    @abstractmethod
    def reset(self) -> None:
        """Reset detector state."""
