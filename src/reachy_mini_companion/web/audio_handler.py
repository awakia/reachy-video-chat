"""FastRTC AsyncStreamHandler bridging WebRTC audio to GeminiSession."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import numpy as np
import soxr

if TYPE_CHECKING:
    from reachy_mini_companion.conversation.gemini_session import GeminiSession

logger = logging.getLogger(__name__)

_INSTALL_HINT = (
    "fastrtc is required for the web dashboard. "
    "Install with: pip install -e '.[dashboard]'"
)

try:
    from fastrtc import AsyncStreamHandler
except ImportError:
    AsyncStreamHandler = object  # type: ignore[misc,assignment]


class WebAudioHandler(AsyncStreamHandler):  # type: ignore[misc]
    """Bridges WebRTC audio from browser to GeminiSession.

    - receive: Browser mic (48kHz) -> resample to 16kHz -> GeminiSession.send_audio()
    - emit: GeminiSession.get_playback_audio() (24kHz PCM16) -> browser speaker
    """

    def __init__(self):
        if AsyncStreamHandler is object:
            raise ImportError(_INSTALL_HINT)
        super().__init__(
            expected_layout="mono",
            output_sample_rate=24000,
            input_sample_rate=48000,
        )
        self._gemini: GeminiSession | None = None
        self._input_rate = 16000   # Gemini expects 16kHz
        self._output_rate = 24000  # Gemini outputs 24kHz
        self._connected = False
        self._on_connection_change: callable | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def set_connection_callback(self, callback: callable) -> None:
        self._on_connection_change = callback

    def copy(self):
        """Return self -- single-user dev tool, no per-connection instances."""
        return self

    async def start_up(self):
        """Called when WebRTC connection is established."""
        self._connected = True
        logger.info("WebRTC audio connected")
        if self._on_connection_change:
            self._on_connection_change(True)

    async def shutdown(self):
        """Called when WebRTC connection is closed."""
        self._connected = False
        logger.info("WebRTC audio disconnected")
        if self._on_connection_change:
            self._on_connection_change(False)

    def attach(self, gemini: GeminiSession) -> None:
        """Attach a GeminiSession for audio bridging."""
        self._gemini = gemini

    def detach(self) -> None:
        """Detach the GeminiSession."""
        self._gemini = None

    async def receive(self, frame: tuple[int, np.ndarray]) -> None:
        """Process incoming WebRTC audio and forward to Gemini."""
        if self._gemini is None:
            return

        sr, audio = frame

        # Squeeze to 1D mono (WebRTC may send (1, N) for mono)
        if audio.ndim > 1:
            audio = audio.squeeze()

        if audio.size == 0:
            return

        # Ensure int16
        if audio.dtype == np.float32:
            audio = (audio * 32767).astype(np.int16)
        elif audio.dtype != np.int16:
            audio = audio.astype(np.int16)

        # Resample to 16kHz if needed
        if sr != self._input_rate:
            audio = soxr.resample(
                audio.astype(np.float64), sr, self._input_rate
            ).astype(np.int16)

        await self._gemini.send_audio(audio.tobytes())

    async def emit(self):
        """Get next audio chunk from Gemini to send to browser."""
        if self._gemini is None:
            await asyncio.sleep(0.04)
            return None

        try:
            audio_bytes = await asyncio.wait_for(
                self._gemini.get_playback_audio(), timeout=0.04
            )
            audio = np.frombuffer(audio_bytes, dtype=np.int16)
            return (self._output_rate, audio)
        except asyncio.TimeoutError:
            return None
