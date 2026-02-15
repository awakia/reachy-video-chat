"""Wake word detection using Edge Impulse (.eim models).

Uses the pre-trained "Hey Reachy" model from HuggingFace:
https://huggingface.co/spaces/luisomoreau/hey_reachy_wake_word_detection
"""

from __future__ import annotations

import logging
import platform
import time
from pathlib import Path

import numpy as np

from reachy_mini_companion.config import USER_DATA_DIR
from reachy_mini_companion.wake.base import BaseWakeWordDetector

logger = logging.getLogger(__name__)

MODELS_DIR = USER_DATA_DIR / "models"

# HuggingFace Space containing the .eim models
HF_SPACE = "luisomoreau/hey_reachy_wake_word_detection"
HF_MODEL_DIR = "hey_reachy_wake_word_detection/models"

# Platform -> model filename mapping
MODEL_FILES: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "hey-reachy-wake-word-detection-mac-arm64.eim",
    ("darwin", "x86_64"): "hey-reachy-wake-word-detection-mac-x86_64.eim",
    ("linux", "aarch64"): "hey-reachy-wake-word-detection-linux-aarch64.eim",
    ("linux", "armv7l"): "hey-reachy-wake-word-detection-linux-armv7.eim",
    ("linux", "x86_64"): "hey-reachy-wake-word-detection-linux-x86_64.eim",
}


def _get_platform_key() -> tuple[str, str]:
    """Get (system, machine) tuple for current platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    return (system, machine)


def _get_model_filename() -> str:
    """Get the appropriate .eim filename for this platform."""
    key = _get_platform_key()
    if key not in MODEL_FILES:
        raise RuntimeError(
            f"No Edge Impulse model available for {key[0]}/{key[1]}. "
            f"Supported: {list(MODEL_FILES.keys())}"
        )
    return MODEL_FILES[key]


def download_hey_reachy_model(dest_dir: Path | None = None) -> Path:
    """Download the Hey Reachy .eim model from HuggingFace.

    Returns the path to the downloaded model file.
    """
    dest_dir = dest_dir or MODELS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = _get_model_filename()
    dest_path = dest_dir / filename

    if dest_path.exists():
        logger.info(f"Model already exists: {dest_path}")
        return dest_path

    logger.info(f"Downloading {filename} from HuggingFace ({HF_SPACE})...")

    try:
        from huggingface_hub import hf_hub_download

        downloaded = hf_hub_download(
            repo_id=HF_SPACE,
            filename=f"{HF_MODEL_DIR}/{filename}",
            repo_type="space",
            local_dir=str(dest_dir),
            local_dir_use_symlinks=False,
        )
        # hf_hub_download may put it in a subdirectory; move to dest_dir root
        downloaded_path = Path(downloaded)
        if downloaded_path != dest_path:
            import shutil
            shutil.move(str(downloaded_path), str(dest_path))
            # Clean up the subdirectory if empty
            sub = dest_dir / HF_MODEL_DIR.split("/")[0]
            if sub.exists() and sub.is_dir():
                shutil.rmtree(sub, ignore_errors=True)

        logger.info(f"Model downloaded to {dest_path}")
        return dest_path

    except ImportError:
        raise ImportError(
            "huggingface_hub is required for auto-download. "
            "Install with: pip install huggingface-hub"
        )


class EdgeImpulseDetector(BaseWakeWordDetector):
    """Detects wake words using Edge Impulse AudioImpulseRunner.

    Unlike openWakeWord which accepts raw audio chunks, Edge Impulse's
    AudioImpulseRunner manages its own audio capture internally. This
    detector wraps that into the common interface.
    """

    def __init__(
        self,
        model_path: str | None = None,
        threshold: float = 0.7,
        refractory_sec: float = 3.0,
    ):
        self.model_path = model_path
        self.threshold = threshold
        self.refractory_sec = refractory_sec

        self._runner = None
        self._last_trigger_time = 0.0

    def load_model(self) -> None:
        """Load the Edge Impulse model, downloading if needed."""
        if self.model_path:
            path = Path(self.model_path)
            if not path.exists():
                raise FileNotFoundError(f"Model not found: {path}")
        else:
            path = download_hey_reachy_model()

        self._model_path = path
        logger.info(f"Edge Impulse model ready: {path}")

        # Don't start the runner here - it will be started in the audio loop
        # since EdgeImpulse manages its own audio capture

    def process_audio(self, audio: np.ndarray) -> bool:
        """Process audio for wake word detection.

        Note: For Edge Impulse, the actual inference happens in the
        classifier loop (run_classifier). This method is provided for
        interface compatibility but the primary detection path is
        run_classifier().
        """
        # Edge Impulse manages its own audio pipeline via AudioImpulseRunner.
        # This method exists for interface compatibility.
        # Use run_classifier() for the real detection loop.
        return False

    async def run_classifier(self, on_detected: callable, stop_event=None) -> None:
        """Run the Edge Impulse classifier loop.

        This is the primary detection method for Edge Impulse. It manages
        its own audio capture and runs inference continuously.

        Args:
            on_detected: Callback when wake word is detected.
            stop_event: asyncio.Event to stop the loop.
        """
        import asyncio

        try:
            from edge_impulse_linux.audio import AudioImpulseRunner
        except ImportError:
            raise ImportError(
                "edge_impulse_linux is required. "
                "Install with: pip install edge_impulse_linux"
            )

        def _run_blocking():
            with AudioImpulseRunner(str(self._model_path)) as runner:
                self._runner = runner
                model_info = runner.init()
                logger.info(
                    f"Edge Impulse runner loaded: "
                    f"{model_info['project']['owner']} / {model_info['project']['name']}"
                )

                for res, audio in runner.classifier():
                    if stop_event and stop_event.is_set():
                        break

                    if "classification" not in res.get("result", {}):
                        continue

                    score = res["result"]["classification"].get("hey_reachy", 0)
                    if score >= self.threshold:
                        now = time.monotonic()
                        if now - self._last_trigger_time >= self.refractory_sec:
                            self._last_trigger_time = now
                            logger.info(f"Wake word detected: hey_reachy (score={score:.3f})")
                            on_detected()

                self._runner = None

        await asyncio.to_thread(_run_blocking)

    def reset(self) -> None:
        """Reset refractory timer."""
        self._last_trigger_time = 0.0
