"""Tests for wake word detection and silence detection."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from reachy_mini_companion.config import WakeConfig
from reachy_mini_companion.wake.vad import SilenceDetector


class TestSilenceDetector:
    def test_no_timeout_with_speech(self):
        """Active speech should not trigger timeout."""
        detector = SilenceDetector(timeout_sec=5.0, rms_threshold=200)
        audio = np.full(1600, 5000, dtype=np.int16)
        assert detector.process(audio) is False

    def test_timeout_with_silence(self):
        """Sustained silence should trigger timeout."""
        detector = SilenceDetector(timeout_sec=2.0, rms_threshold=200)
        silent_audio = np.zeros(1600, dtype=np.int16)

        assert detector.process(silent_audio, current_time=0.0) is False
        assert detector.process(silent_audio, current_time=1.0) is False
        assert detector.process(silent_audio, current_time=2.5) is True

    def test_speech_resets_timer(self):
        """Speech after silence should reset the timer."""
        detector = SilenceDetector(timeout_sec=2.0, rms_threshold=200)
        silent = np.zeros(1600, dtype=np.int16)
        loud = np.full(1600, 5000, dtype=np.int16)

        detector.process(silent, current_time=0.0)
        detector.process(silent, current_time=1.5)
        detector.process(loud, current_time=1.5)
        assert detector.process(silent, current_time=2.5) is False
        assert detector.process(silent, current_time=4.0) is True

    def test_reset(self):
        detector = SilenceDetector(timeout_sec=1.0, rms_threshold=200)
        silent = np.zeros(1600, dtype=np.int16)
        detector.process(silent, current_time=0.0)
        detector.reset()
        assert detector.process(silent, current_time=0.5) is False

    def test_float32_input(self):
        detector = SilenceDetector(timeout_sec=1.0, rms_threshold=200)
        loud = np.full(1600, 0.5, dtype=np.float32)
        assert detector.process(loud) is False


class TestOpenWakeWordDetector:
    def test_import_error_without_openwakeword(self):
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector

        detector = OpenWakeWordDetector()
        try:
            detector.load_model()
        except ImportError:
            pass  # Expected on dev machines without openwakeword

    def test_process_without_loading_raises(self):
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector

        detector = OpenWakeWordDetector()
        audio = np.zeros(1600, dtype=np.int16)
        with pytest.raises(RuntimeError, match="not loaded"):
            detector.process_audio(audio)

    def test_float32_conversion(self):
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector, FRAME_SAMPLES

        detector = OpenWakeWordDetector(threshold=0.5)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.1}

        audio = np.zeros(FRAME_SAMPLES, dtype=np.float32)
        result = detector.process_audio(audio)
        assert result is False
        detector._model.predict.assert_called_once()

    def test_stereo_to_mono(self):
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector, FRAME_SAMPLES

        detector = OpenWakeWordDetector(threshold=0.5)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.0}

        stereo = np.zeros((FRAME_SAMPLES, 2), dtype=np.int16)
        detector.process_audio(stereo)
        detector._model.predict.assert_called_once()

    def test_refractory_period(self):
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector, FRAME_SAMPLES

        detector = OpenWakeWordDetector(threshold=0.5, refractory_sec=3.0)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.9}

        audio = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        assert detector.process_audio(audio) is True
        assert detector.process_audio(audio) is False


class TestEdgeImpulseDetector:
    def test_init(self):
        from reachy_mini_companion.wake.edge_impulse import EdgeImpulseDetector

        detector = EdgeImpulseDetector(threshold=0.8, refractory_sec=2.0)
        assert detector.threshold == 0.8
        assert detector.refractory_sec == 2.0

    def test_reset(self):
        from reachy_mini_companion.wake.edge_impulse import EdgeImpulseDetector

        detector = EdgeImpulseDetector()
        detector._last_trigger_time = 999.0
        detector.reset()
        assert detector._last_trigger_time == 0.0

    def test_get_model_filename(self):
        from reachy_mini_companion.wake.edge_impulse import _get_model_filename

        filename = _get_model_filename()
        assert filename.startswith("hey-reachy-wake-word-detection-")
        assert filename.endswith(".eim")

    def test_platform_key(self):
        from reachy_mini_companion.wake.edge_impulse import _get_platform_key

        system, machine = _get_platform_key()
        assert system in ("darwin", "linux")
        assert len(machine) > 0


class TestCreateWakeDetector:
    def test_create_edge_impulse(self):
        from reachy_mini_companion.wake import create_wake_detector
        from reachy_mini_companion.wake.edge_impulse import EdgeImpulseDetector

        config = WakeConfig(backend="edge_impulse", threshold=0.8)
        detector = create_wake_detector(config)
        assert isinstance(detector, EdgeImpulseDetector)
        assert detector.threshold == 0.8

    def test_create_openwakeword(self):
        from reachy_mini_companion.wake import create_wake_detector
        from reachy_mini_companion.wake.wake_word import OpenWakeWordDetector

        config = WakeConfig(backend="openwakeword", model="hey_jarvis", threshold=0.5)
        detector = create_wake_detector(config)
        assert isinstance(detector, OpenWakeWordDetector)
        assert detector.model_name == "hey_jarvis"
        assert detector.threshold == 0.5

    def test_create_unknown_backend(self):
        from reachy_mini_companion.wake import create_wake_detector

        config = WakeConfig(backend="nonexistent")
        with pytest.raises(ValueError, match="Unknown wake word backend"):
            create_wake_detector(config)

    def test_custom_model_path_passed(self):
        from reachy_mini_companion.wake import create_wake_detector
        from reachy_mini_companion.wake.edge_impulse import EdgeImpulseDetector

        config = WakeConfig(backend="edge_impulse", custom_model_path="/tmp/my.eim")
        detector = create_wake_detector(config)
        assert isinstance(detector, EdgeImpulseDetector)
        assert detector.model_path == "/tmp/my.eim"
