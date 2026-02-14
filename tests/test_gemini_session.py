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
    kind, data = session._send_queue.get_nowait()
    assert kind == "audio"
    assert data == b"\x00" * 3200


async def test_send_image_queues():
    """send_image should queue image bytes."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    await session.send_image(b"\xff\xd8\xff")
    kind, data = session._send_queue.get_nowait()
    assert kind == "image"
    assert data == b"\xff\xd8\xff"


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


def test_build_config_includes_resumption():
    """_build_config should include session_resumption and context_window_compression."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    live_config = session._build_config()
    assert live_config.session_resumption is not None
    assert live_config.session_resumption.handle is None
    assert live_config.context_window_compression is not None
    assert live_config.context_window_compression.sliding_window is not None


def test_build_config_with_resumption_handle():
    """_build_config should include the resumption handle when set."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    session._resumption_handle = "test-handle-123"
    live_config = session._build_config()
    assert live_config.session_resumption.handle == "test-handle-123"


def test_permanent_error_detection():
    """_is_permanent_error should detect auth/quota/config errors."""
    assert GeminiSession._is_permanent_error(Exception("Invalid API key"))
    assert GeminiSession._is_permanent_error(Exception("UNAUTHENTICATED"))
    assert GeminiSession._is_permanent_error(Exception("403 Forbidden"))
    assert GeminiSession._is_permanent_error(Exception("401 Unauthorized"))
    assert GeminiSession._is_permanent_error(Exception("quota exceeded"))
    assert GeminiSession._is_permanent_error(Exception("permission denied"))
    assert GeminiSession._is_permanent_error(Exception("not supported in Gemini API"))
    # ValueError/TypeError are always permanent (invalid config)
    assert GeminiSession._is_permanent_error(ValueError("transparent not supported"))
    assert GeminiSession._is_permanent_error(TypeError("invalid argument"))
    # Transient errors should not be permanent
    assert not GeminiSession._is_permanent_error(Exception("connection reset"))
    assert not GeminiSession._is_permanent_error(Exception("timeout"))
    assert not GeminiSession._is_permanent_error(Exception("server error"))


async def test_receiver_handles_go_away():
    """Receiver should set _go_away_received and _reconnect_event on go_away."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    session._reconnect_event = asyncio.Event()
    stop_event = asyncio.Event()

    # Mock session that yields one go_away response then ends
    mock_response = MagicMock()
    mock_response.server_content = None
    mock_response.tool_call = None
    mock_response.go_away = MagicMock()
    mock_response.go_away.time_left = "30s"
    mock_response.session_resumption_update = None

    mock_session = AsyncMock()

    async def mock_receive():
        yield mock_response

    mock_session.receive = mock_receive
    session._session = mock_session

    await session._receiver_loop(stop_event)

    assert session._go_away_received is True
    assert session._reconnect_event.is_set()


async def test_receiver_saves_resumption_handle():
    """Receiver should save new resumption handles from server."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    session._reconnect_event = asyncio.Event()
    stop_event = asyncio.Event()

    # Mock response with session_resumption_update
    mock_response = MagicMock()
    mock_response.server_content = None
    mock_response.tool_call = None
    mock_response.go_away = None
    mock_response.session_resumption_update = MagicMock()
    mock_response.session_resumption_update.new_handle = "handle-abc"
    mock_response.session_resumption_update.resumable = True

    mock_session = AsyncMock()

    async def mock_receive():
        yield mock_response

    mock_session.receive = mock_receive
    session._session = mock_session

    await session._receiver_loop(stop_event)

    assert session._resumption_handle == "handle-abc"
    assert session._reconnect_event.is_set()


async def test_receiver_ignores_non_resumable_handle():
    """Receiver should not save handle when resumable is False."""
    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config)
    session._reconnect_event = asyncio.Event()
    stop_event = asyncio.Event()

    mock_response = MagicMock()
    mock_response.server_content = None
    mock_response.tool_call = None
    mock_response.go_away = None
    mock_response.session_resumption_update = MagicMock()
    mock_response.session_resumption_update.new_handle = "handle-xyz"
    mock_response.session_resumption_update.resumable = False

    mock_session = AsyncMock()

    async def mock_receive():
        yield mock_response

    mock_session.receive = mock_receive
    session._session = mock_session

    await session._receiver_loop(stop_event)

    assert session._resumption_handle is None


async def test_on_status_callback():
    """on_status callback should be called with status strings."""
    statuses = []

    config = AppConfig(google_api_key="test-key")
    session = GeminiSession(config=config, on_status=lambda s: statuses.append(s))

    stop_event = asyncio.Event()

    # Mock the client and connection
    mock_session = AsyncMock()

    async def mock_receive():
        # Set stop_event after connection is established so we capture statuses
        stop_event.set()
        return
        yield  # Make it an empty async generator

    mock_session.receive = mock_receive

    mock_connect = AsyncMock()
    mock_connect.__aenter__ = AsyncMock(return_value=mock_session)
    mock_connect.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.aio.live.connect.return_value = mock_connect

    with patch("reachy_mini_companion.conversation.gemini_session.genai") as mock_genai:
        mock_genai.Client.return_value = mock_client
        await session.run(stop_event)

    assert "connecting" in statuses
    assert "connected" in statuses
