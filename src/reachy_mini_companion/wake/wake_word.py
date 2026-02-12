"""Wake word detection using openWakeWord."""

from __future__ import annotations

import logging
import time

import numpy as np

from reachy_mini_companion.wake.base import BaseWakeWordDetector

logger = logging.getLogger(__name__)

FRAME_MS = 80  # openWakeWord expects 80ms frames
SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 1280 samples per frame


class OpenWakeWordDetector(BaseWakeWordDetector):
    """Detects wake words in audio streams using openWakeWord."""

    def __init__(
        self,
        model_name: str = "hey_jarvis",
        custom_model_path: str | None = None,
        threshold: float = 0.5,
        refractory_sec: float = 3.0,
    ):
        self.model_name = model_name
        self.custom_model_path = custom_model_path
        self.threshold = threshold
        self.refractory_sec = refractory_sec

        self._model = None
        self._buffer = np.array([], dtype=np.int16)
        self._last_trigger_time = 0.0

    def load_model(self) -> None:
        """Load the openWakeWord model."""
        try:
            from openwakeword.model import Model

            if self.custom_model_path:
                self._model = Model(
                    wakeword_models=[self.custom_model_path],
                    inference_framework="onnx",
                )
            else:
                self._model = Model(
                    wakeword_models=[self.model_name],
                )
            logger.info(f"openWakeWord model loaded: {self.model_name}")
        except ImportError:
            logger.warning(
                "openwakeword not installed. Install with: pip install 'reachy-mini-companion[wake]'"
            )
            raise

    def process_audio(self, audio: np.ndarray) -> bool:
        """Process audio chunk and detect wake word.

        Args:
            audio: Audio samples (int16 mono 16kHz or float32 to be converted).

        Returns:
            True if wake word detected (respecting refractory period).
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Convert float32 to int16 if needed
        if audio.dtype == np.float32:
            audio = (audio * 32767).astype(np.int16)

        # Convert stereo to mono if needed
        if audio.ndim == 2:
            audio = audio.mean(axis=1).astype(np.int16)

        # Accumulate in buffer
        self._buffer = np.concatenate([self._buffer, audio])

        # Process complete frames
        detected = False
        while len(self._buffer) >= FRAME_SAMPLES:
            frame = self._buffer[:FRAME_SAMPLES]
            self._buffer = self._buffer[FRAME_SAMPLES:]

            prediction = self._model.predict(frame)

            for model_name, score in prediction.items():
                if score >= self.threshold:
                    now = time.monotonic()
                    if now - self._last_trigger_time >= self.refractory_sec:
                        self._last_trigger_time = now
                        detected = True
                        logger.info(f"Wake word detected: {model_name} (score={score:.3f})")

        return detected

    def reset(self) -> None:
        """Reset buffer and refractory timer."""
        self._buffer = np.array([], dtype=np.int16)
        self._last_trigger_time = 0.0
        if self._model is not None:
            self._model.reset()


# Keep old name as alias for backwards compatibility
WakeWordDetector = OpenWakeWordDetector
