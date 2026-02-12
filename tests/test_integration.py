"""Integration tests for the full application lifecycle."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from reachy_mini_companion.config import AppConfig
from reachy_mini_companion.state_machine import Event, State, StateMachine


def test_full_state_flow():
    """Complete state machine lifecycle with all transitions."""
    sm = StateMachine()

    # SETUP -> SLEEPING
    assert sm.send_event(Event.SETUP_COMPLETE) == State.SLEEPING

    # SLEEPING -> WAKING
    assert sm.send_event(Event.WAKE_WORD_DETECTED) == State.WAKING

    # WAKING -> ACTIVE
    assert sm.send_event(Event.SESSION_READY) == State.ACTIVE

    # ACTIVE -> COOLDOWN (silence timeout)
    assert sm.send_event(Event.SILENCE_TIMEOUT) == State.COOLDOWN

    # COOLDOWN -> SLEEPING
    assert sm.send_event(Event.COOLDOWN_COMPLETE) == State.SLEEPING

    # Second cycle with max duration
    assert sm.send_event(Event.WAKE_WORD_DETECTED) == State.WAKING
    assert sm.send_event(Event.SESSION_READY) == State.ACTIVE
    assert sm.send_event(Event.MAX_DURATION) == State.COOLDOWN
    assert sm.send_event(Event.COOLDOWN_COMPLETE) == State.SLEEPING


def test_error_recovery_flow():
    """Error in any state should recover gracefully."""
    # Error during WAKING -> back to SLEEPING
    sm = StateMachine(initial_state=State.WAKING)
    assert sm.send_event(Event.ERROR) == State.SLEEPING

    # Error during ACTIVE -> COOLDOWN
    sm = StateMachine(initial_state=State.ACTIVE)
    assert sm.send_event(Event.ERROR) == State.COOLDOWN

    # Error during COOLDOWN -> SLEEPING
    sm = StateMachine(initial_state=State.COOLDOWN)
    assert sm.send_event(Event.ERROR) == State.SLEEPING


async def test_companion_app_setup(tmp_path):
    """CompanionApp should set up in simulate mode without errors."""
    from reachy_mini_companion.main import CompanionApp

    config = AppConfig(
        google_api_key="test-key",
    )
    config.reachy.simulate = True
    config.cost.db_path = str(tmp_path / "test.db")

    app = CompanionApp(config)
    await app.setup()

    assert app._sm is not None
    assert app._sm.state == State.SLEEPING
    assert app._controller is not None
    assert app._dispatcher is not None

    await app.cleanup()


async def test_companion_app_waking(tmp_path):
    """WAKING state should transition to ACTIVE on success."""
    from reachy_mini_companion.main import CompanionApp

    config = AppConfig(google_api_key="test-key")
    config.reachy.simulate = True
    config.cost.db_path = str(tmp_path / "test.db")

    app = CompanionApp(config)
    await app.setup()

    # Manually set to WAKING state
    app._sm.send_event(Event.WAKE_WORD_DETECTED)
    assert app._sm.state == State.WAKING

    await app._handle_waking()
    assert app._sm.state == State.ACTIVE

    await app.cleanup()


async def test_companion_app_cooldown(tmp_path):
    """COOLDOWN should transition back to SLEEPING."""
    from reachy_mini_companion.main import CompanionApp

    config = AppConfig(google_api_key="test-key")
    config.reachy.simulate = True
    config.cost.db_path = str(tmp_path / "test.db")
    config.session.cooldown_sec = 0  # Skip cooldown wait

    app = CompanionApp(config)
    await app.setup()

    # Get to COOLDOWN state
    app._sm.send_event(Event.WAKE_WORD_DETECTED)
    app._sm.send_event(Event.SESSION_READY)
    app._sm.send_event(Event.SILENCE_TIMEOUT)
    assert app._sm.state == State.COOLDOWN

    await app._handle_cooldown()
    assert app._sm.state == State.SLEEPING

    await app.cleanup()


def test_config_smoke_test():
    """Config should load and have expected structure."""
    from reachy_mini_companion.config import load_config

    config = load_config()
    assert config.reachy.host == "reachy2.local"
    assert config.gemini.model == "gemini-2.5-flash-native-audio-preview-12-2025"
    assert config.session.max_duration_sec == 300
    assert config.cost.pricing.input_audio_per_million == 0.70
    assert config.web_ui.port == 7860


def test_tool_declarations_valid():
    """Tool declarations should be valid and complete."""
    from reachy_mini_companion.tools.core_tools import create_tool_declarations
    from reachy_mini_companion.robot.expressions import EXPRESSIONS, LOOK_DIRECTIONS

    tools = create_tool_declarations()
    assert len(tools) == 1

    decl_names = [fd.name for fd in tools[0].function_declarations]
    assert "robot_expression" in decl_names
    assert "robot_look_at" in decl_names

    # Check all expressions are enumerated
    expr_decl = next(fd for fd in tools[0].function_declarations if fd.name == "robot_expression")
    action_enum = expr_decl.parameters.properties["action"].enum
    for action in EXPRESSIONS:
        assert action in action_enum
