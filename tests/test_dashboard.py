"""Tests for dashboard state and audio handler (no fastrtc required)."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import numpy as np

# --- Mock fastrtc before importing audio_handler ---
# This allows tests to run without fastrtc installed.
if "fastrtc" not in sys.modules:

    class _StubAsyncStreamHandler:
        def __init__(self, **kwargs):
            pass

    class _StubWebRTC:
        """Stub for fastrtc.WebRTC Gradio component."""
        def __init__(self, **kwargs):
            pass

        def stream(self, **kwargs):
            pass

    _mock_fastrtc = MagicMock()
    _mock_fastrtc.AsyncStreamHandler = _StubAsyncStreamHandler
    _mock_fastrtc.WebRTC = _StubWebRTC
    sys.modules["fastrtc"] = _mock_fastrtc

from reachy_mini_companion.web.audio_handler import WebAudioHandler
from reachy_mini_companion.web.dashboard import DashboardState


class TestDashboardState:
    def test_initial_state(self):
        ds = DashboardState()
        assert ds.state == "SETUP"
        assert ds.expression == ""
        assert ds.look_direction == ""

    def test_update_state(self):
        ds = DashboardState()
        ds.update_state("SLEEPING")
        assert ds.state == "SLEEPING"

    def test_update_expression(self):
        ds = DashboardState()
        ds.update_expression("nod")
        assert ds.expression == "nod"

    def test_update_look(self):
        ds = DashboardState()
        ds.update_look("left")
        assert ds.look_direction == "left"

    def test_get_status(self):
        ds = DashboardState()
        ds.update_state("ACTIVE")
        ds.detail = "Gemini connected"
        ds.update_expression("surprise")
        ds.update_look("up")
        assert ds.get_status() == ("ACTIVE", "Gemini connected", "surprise", "up", "", False, [])

    def test_audio_connected(self):
        ds = DashboardState()
        assert ds.audio_connected is False
        ds.audio_connected = True
        assert ds.get_status()[5] is True

    def test_set_and_clear_error(self):
        ds = DashboardState()
        ds.set_error("API key invalid")
        assert ds.last_error == "API key invalid"
        assert ds.get_status()[4] == "API key invalid"
        ds.clear_error()
        assert ds.last_error == ""

    def test_append_transcript_user(self):
        ds = DashboardState()
        ds.append_transcript("user", "Hello ", False)
        ds.append_transcript("user", "world", True)
        assert len(ds.transcript) == 1
        assert ds.transcript[0] == {"role": "user", "content": "Hello world"}

    def test_append_transcript_assistant(self):
        ds = DashboardState()
        ds.append_transcript("assistant", "Hi ", False)
        ds.append_transcript("assistant", "there!", True)
        assert len(ds.transcript) == 1
        assert ds.transcript[0] == {"role": "assistant", "content": "Hi there!"}

    def test_transcript_in_progress_display(self):
        ds = DashboardState()
        ds.append_transcript("user", "Hello", False)
        display = ds.get_transcript_for_display()
        assert len(display) == 1
        assert display[0] == {"role": "user", "content": "Hello ..."}

    def test_transcript_in_get_status(self):
        ds = DashboardState()
        ds.append_transcript("user", "test", True)
        status = ds.get_status()
        assert status[6] == [{"role": "user", "content": "test"}]

    def test_clear_transcript(self):
        ds = DashboardState()
        ds.append_transcript("user", "test", True)
        ds.append_transcript("assistant", "partial", False)
        ds.clear_transcript()
        assert ds.transcript == []
        assert ds.user_text_buffer == ""
        assert ds.assistant_text_buffer == ""


class TestWebAudioHandler:
    def test_copy_returns_self(self):
        handler = WebAudioHandler()
        result = handler.copy()
        assert result is handler

    def test_attach_detach(self):
        handler = WebAudioHandler()
        gemini = MagicMock()
        handler.attach(gemini)
        assert handler._gemini is gemini
        handler.detach()
        assert handler._gemini is None

    async def test_receive_ignored_without_gemini(self):
        handler = WebAudioHandler()
        frame = (48000, np.zeros(960, dtype=np.int16))
        await handler.receive(frame)  # Should not raise

    async def test_receive_forwards_16khz_audio(self):
        handler = WebAudioHandler()
        gemini = AsyncMock()
        handler.attach(gemini)

        audio = np.ones(160, dtype=np.int16) * 100
        await handler.receive((16000, audio))

        gemini.send_audio.assert_called_once()
        sent = gemini.send_audio.call_args[0][0]
        assert isinstance(sent, bytes)
        assert len(sent) == 160 * 2  # int16 = 2 bytes per sample

    async def test_receive_resamples_48khz(self):
        handler = WebAudioHandler()
        gemini = AsyncMock()
        handler.attach(gemini)

        # 480 samples at 48kHz = 10ms of audio
        audio = np.ones(480, dtype=np.int16) * 100
        await handler.receive((48000, audio))

        gemini.send_audio.assert_called_once()
        sent = gemini.send_audio.call_args[0][0]
        assert isinstance(sent, bytes)
        # After resampling 48kHz -> 16kHz, expect ~160 samples (10ms at 16kHz)
        samples = len(sent) // 2
        assert 150 <= samples <= 170

    async def test_receive_converts_float32(self):
        handler = WebAudioHandler()
        gemini = AsyncMock()
        handler.attach(gemini)

        audio = np.ones(160, dtype=np.float32) * 0.5
        await handler.receive((16000, audio))

        gemini.send_audio.assert_called_once()

    async def test_emit_returns_none_without_gemini(self):
        handler = WebAudioHandler()
        result = await handler.emit()
        assert result is None

    async def test_emit_returns_audio(self):
        handler = WebAudioHandler()
        gemini = AsyncMock()
        audio_data = (np.ones(960, dtype=np.int16) * 100).tobytes()
        gemini.get_playback_audio.return_value = audio_data
        handler.attach(gemini)

        result = await handler.emit()
        assert result is not None
        sr, audio = result
        assert sr == 24000
        assert len(audio) == 960

    async def test_emit_returns_none_on_timeout(self):
        handler = WebAudioHandler()
        gemini = AsyncMock()

        async def slow():
            await asyncio.sleep(1.0)

        gemini.get_playback_audio = slow
        handler.attach(gemini)

        result = await handler.emit()
        assert result is None
