"""Audio bridge between Reachy Mini robot and the Gemini session."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import numpy as np
import soxr

from reachy_mini_companion.config import AppConfig

logger = logging.getLogger(__name__)

SendCallback = Callable[[bytes], asyncio.coroutines]
GetAudioCallback = Callable[[], asyncio.coroutines]


class RobotAudioBridge:
    """Bridges audio between the robot's mic/speaker and Gemini.

    - Captures audio from robot mic -> converts to 16kHz PCM16 mono -> sends to Gemini
    - Receives 24kHz PCM16 from Gemini -> resamples to 16kHz -> plays on robot speaker
    """

    def __init__(self, robot, config: AppConfig):
        self.robot = robot
        self.config = config
        self._input_rate = config.gemini.input_sample_rate  # 16kHz
        self._output_rate = config.gemini.output_sample_rate  # 24kHz

    async def capture_loop(
        self,
        send_callback: SendCallback,
        stop_event: asyncio.Event,
    ) -> None:
        """Capture audio from robot mic and send via callback.

        Args:
            send_callback: Async callback to send audio bytes.
            stop_event: Event to signal stop.
        """
        logger.info("Audio capture loop started")

        while not stop_event.is_set():
            try:
                if self.robot is None:
                    await asyncio.sleep(0.1)
                    continue

                # Get audio sample from robot (blocking SDK call)
                audio = await asyncio.to_thread(self.robot.media.get_audio_sample)

                if audio is None:
                    await asyncio.sleep(0.01)
                    continue

                # Convert to int16 mono if needed
                if isinstance(audio, np.ndarray):
                    if audio.dtype == np.float32:
                        audio = (audio * 32767).astype(np.int16)
                    if audio.ndim == 2:
                        audio = audio.mean(axis=1).astype(np.int16)

                await send_callback(audio.tobytes())

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not stop_event.is_set():
                    logger.error(f"Audio capture error: {e}")
                await asyncio.sleep(0.1)

        logger.info("Audio capture loop stopped")

    async def playback_loop(
        self,
        get_audio_callback: GetAudioCallback,
        stop_event: asyncio.Event,
    ) -> None:
        """Receive audio from Gemini and play on robot speaker.

        Args:
            get_audio_callback: Async callback to get audio bytes (24kHz PCM16).
            stop_event: Event to signal stop.
        """
        logger.info("Audio playback loop started")

        while not stop_event.is_set():
            try:
                audio_bytes = await get_audio_callback()

                if self.robot is None:
                    continue

                # Convert bytes to numpy array (24kHz PCM16)
                audio = np.frombuffer(audio_bytes, dtype=np.int16)

                # Resample from 24kHz to 16kHz for robot speaker
                if self._output_rate != self._input_rate:
                    audio_float = audio.astype(np.float64)
                    resampled = soxr.resample(
                        audio_float, self._output_rate, self._input_rate
                    )
                    audio = resampled.astype(np.int16)

                # Send to robot speaker (blocking SDK call)
                await asyncio.to_thread(self.robot.media.push_audio_sample, audio)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if not stop_event.is_set():
                    logger.error(f"Audio playback error: {e}")
                await asyncio.sleep(0.01)

        logger.info("Audio playback loop stopped")
