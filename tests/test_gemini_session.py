"""Tests for Gemini Live API session."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reachy_mini_companion.config import AppConfig
from reachy_mini_companion.conversation.gemini_session import GeminiSession
from reachy_mini_companion.conversation.system_prompt import (
    load_enabled_tools,
    load_system_prompt,
)


def test_load_default_system_prompt():
    """Default profile instructions.txt should load."""
    prompt = load_system_prompt("default")
    assert len(prompt) > 0
    assert "Reachy" in prompt


def test_load_kids_system_prompt():
    prompt = load_system_prompt("kids")
    assert len(prompt) > 0


def test_load_missing_profile_fallback():
    prompt = load_system_prompt("nonexistent_profile")
    assert "Reachy" in prompt


def test_load_enabled_tools():
    tools = load_enabled_tools("default")
    assert "robot_expression" in tools
    assert "robot_look_at" in tools


def test_load_enabled_tools_missing_profile():
    tools = load_enabled_tools("nonexistent")
    assert len(tools) > 0  # Should return defaults


def test_build_config():
    """Should build a valid LiveConnectConfig."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    live_config = session._build_config()
    assert live_config.response_modalities == ["AUDIO"]
    assert live_config.system_instruction is not None


def test_build_config_with_tools():
    """Should filter tools by enabled list."""
    from google.genai import types

    config = AppConfig(google_api_key="test-key")
    tool_declarations = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="robot_expression",
                    description="test",
                    parameters=types.Schema(type="OBJECT", properties={}),
                ),
                types.FunctionDeclaration(
                    name="disabled_tool",
                    description="test",
                    parameters=types.Schema(type="OBJECT", properties={}),
                ),
            ]
        )
    ]
    session = GeminiSession(config=config, tool_declarations=tool_declarations)
    live_config = session._build_config()
    # Should have filtered out disabled_tool
    assert live_config.tools is not None
    names = [
        fd.name
        for tool in live_config.tools
        for fd in tool.function_declarations
    ]
    assert "robot_expression" in names
    assert "disabled_tool" not in names


async def test_send_audio_queues():
    """send_audio should queue audio bytes."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    await session.send_audio(b"\x00" * 3200)
    assert not session._send_queue.empty()
    msg = session._send_queue.get_nowait()
    assert msg["mime_type"] == "audio/pcm"


async def test_send_image_queues():
    """send_image should queue image bytes."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    await session.send_image(b"\xff\xd8\xff")
    msg = session._send_queue.get_nowait()
    assert msg["mime_type"] == "image/jpeg"


async def test_tool_call_handler():
    """Tool calls should be dispatched to the handler."""
    results = []

    async def handler(name, args):
        results.append((name, args))
        return "ok"

    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config, on_tool_call=handler)

    # Create mock function call
    mock_fc = MagicMock()
    mock_fc.name = "robot_expression"
    mock_fc.args = {"action": "nod"}

    # Mock session for sending tool response
    session._session = AsyncMock()

    await session._handle_tool_calls([mock_fc])
    assert len(results) == 1
    assert results[0] == ("robot_expression", {"action": "nod"})
