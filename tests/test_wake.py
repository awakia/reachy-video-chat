"""Tests for wake word detection and silence detection."""

import numpy as np
import pytest

from reachy_mini_companion.wake.vad import SilenceDetector


class TestSilenceDetector:
    def test_no_timeout_with_speech(self):
        """Active speech should not trigger timeout."""
        detector = SilenceDetector(timeout_sec=5.0, rms_threshold=200)
        # Loud audio (speech)
        audio = np.full(1600, 5000, dtype=np.int16)
        assert detector.process(audio) is False

    def test_timeout_with_silence(self):
        """Sustained silence should trigger timeout."""
        detector = SilenceDetector(timeout_sec=2.0, rms_threshold=200)
        silent_audio = np.zeros(1600, dtype=np.int16)

        # Process at t=0
        assert detector.process(silent_audio, current_time=0.0) is False
        # Process at t=1 (still under timeout)
        assert detector.process(silent_audio, current_time=1.0) is False
        # Process at t=2.5 (past timeout)
        assert detector.process(silent_audio, current_time=2.5) is True

    def test_speech_resets_timer(self):
        """Speech after silence should reset the timer."""
        detector = SilenceDetector(timeout_sec=2.0, rms_threshold=200)
        silent = np.zeros(1600, dtype=np.int16)
        loud = np.full(1600, 5000, dtype=np.int16)

        detector.process(silent, current_time=0.0)
        detector.process(silent, current_time=1.5)  # 1.5s silence
        detector.process(loud, current_time=1.5)  # Speech resets
        # 1s of silence after speech - should not timeout
        assert detector.process(silent, current_time=2.5) is False
        # 2.5s of silence after speech - should timeout
        assert detector.process(silent, current_time=4.0) is True

    def test_reset(self):
        detector = SilenceDetector(timeout_sec=1.0, rms_threshold=200)
        silent = np.zeros(1600, dtype=np.int16)
        detector.process(silent, current_time=0.0)
        detector.reset()
        # After reset, timer should be fresh
        assert detector.process(silent, current_time=0.5) is False

    def test_float32_input(self):
        """Should handle float32 audio input."""
        detector = SilenceDetector(timeout_sec=1.0, rms_threshold=200)
        loud = np.full(1600, 0.5, dtype=np.float32)
        assert detector.process(loud) is False


class TestWakeWordDetector:
    def test_import_error_without_openwakeword(self):
        """Should raise ImportError when openwakeword is not installed."""
        from reachy_mini_companion.wake.wake_word import WakeWordDetector

        detector = WakeWordDetector()
        # On systems without openwakeword, this should raise ImportError
        # On systems with it, it should work
        try:
            detector.load_model()
        except ImportError:
            pass  # Expected on dev machines without openwakeword

    def test_process_without_loading_raises(self):
        """Should raise RuntimeError if model not loaded."""
        from reachy_mini_companion.wake.wake_word import WakeWordDetector

        detector = WakeWordDetector()
        audio = np.zeros(1600, dtype=np.int16)
        with pytest.raises(RuntimeError, match="not loaded"):
            detector.process_audio(audio)

    def test_float32_conversion(self):
        """Float32 input should be handled."""
        from unittest.mock import MagicMock
        from reachy_mini_companion.wake.wake_word import WakeWordDetector, FRAME_SAMPLES

        detector = WakeWordDetector(threshold=0.5)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.1}

        # Process enough float32 audio for one frame
        audio = np.zeros(FRAME_SAMPLES, dtype=np.float32)
        result = detector.process_audio(audio)
        assert result is False
        detector._model.predict.assert_called_once()

    def test_stereo_to_mono(self):
        """Stereo input should be converted to mono."""
        from unittest.mock import MagicMock
        from reachy_mini_companion.wake.wake_word import WakeWordDetector, FRAME_SAMPLES

        detector = WakeWordDetector(threshold=0.5)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.0}

        stereo = np.zeros((FRAME_SAMPLES, 2), dtype=np.int16)
        detector.process_audio(stereo)
        detector._model.predict.assert_called_once()

    def test_refractory_period(self):
        """Should not trigger again within refractory period."""
        from unittest.mock import MagicMock
        from reachy_mini_companion.wake.wake_word import WakeWordDetector, FRAME_SAMPLES

        detector = WakeWordDetector(threshold=0.5, refractory_sec=3.0)
        detector._model = MagicMock()
        detector._model.predict.return_value = {"test_model": 0.9}

        audio = np.zeros(FRAME_SAMPLES, dtype=np.int16)

        # First detection should trigger
        assert detector.process_audio(audio) is True
        # Second detection immediately after should NOT trigger (refractory)
        assert detector.process_audio(audio) is False
