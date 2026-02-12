"""Sound effect playback for state transitions."""

from __future__ import annotations

import asyncio
import logging
import wave
from pathlib import Path

import numpy as np

from reachy_mini_companion.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

SOUNDS_DIR = PROJECT_ROOT / "sounds"


def _load_wav(path: Path) -> np.ndarray | None:
    """Load a WAV file as int16 numpy array."""
    if not path.exists():
        logger.warning(f"Sound file not found: {path}")
        return None
    try:
        with wave.open(str(path), "r") as wf:
            frames = wf.readframes(wf.getnframes())
            return np.frombuffer(frames, dtype=np.int16)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return None


class SoundPlayer:
    """Plays notification sounds on robot speaker or local audio."""

    def __init__(self, robot=None):
        self.robot = robot

    async def play(self, name: str) -> None:
        """Play a sound by name (e.g., 'wake_up', 'sleep', 'error')."""
        path = SOUNDS_DIR / f"{name}.wav"
        audio = _load_wav(path)
        if audio is None:
            return

        logger.info(f"Playing sound: {name}")

        if self.robot is not None:
            try:
                await asyncio.to_thread(self.robot.media.push_audio_sample, audio)
            except Exception as e:
                logger.warning(f"Failed to play on robot: {e}")
        else:
            logger.info(f"[Simulate] sound: {name} ({len(audio)/16000:.2f}s)")

    async def play_wake_up(self) -> None:
        await self.play("wake_up")

    async def play_sleep(self) -> None:
        await self.play("sleep")

    async def play_error(self) -> None:
        await self.play("error")
