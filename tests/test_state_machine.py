"""Tests for state machine."""

import pytest

from reachy_mini_companion.state_machine import Event, State, StateMachine


def test_initial_state():
    sm = StateMachine()
    assert sm.state == State.SETUP


def test_custom_initial_state():
    sm = StateMachine(initial_state=State.SLEEPING)
    assert sm.state == State.SLEEPING


def test_happy_path():
    """Full lifecycle: SETUP -> SLEEPING -> WAKING -> ACTIVE -> COOLDOWN -> SLEEPING."""
    sm = StateMachine()
    assert sm.send_event(Event.SETUP_COMPLETE) == State.SLEEPING
    assert sm.send_event(Event.WAKE_WORD_DETECTED) == State.WAKING
    assert sm.send_event(Event.SESSION_READY) == State.ACTIVE
    assert sm.send_event(Event.SILENCE_TIMEOUT) == State.COOLDOWN
    assert sm.send_event(Event.COOLDOWN_COMPLETE) == State.SLEEPING


def test_max_duration_ends_active():
    sm = StateMachine(initial_state=State.ACTIVE)
    assert sm.send_event(Event.MAX_DURATION) == State.COOLDOWN


def test_error_in_active_goes_to_cooldown():
    sm = StateMachine(initial_state=State.ACTIVE)
    assert sm.send_event(Event.ERROR) == State.COOLDOWN


def test_error_in_waking_goes_to_sleeping():
    sm = StateMachine(initial_state=State.WAKING)
    assert sm.send_event(Event.ERROR) == State.SLEEPING


def test_error_in_cooldown_goes_to_sleeping():
    sm = StateMachine(initial_state=State.COOLDOWN)
    assert sm.send_event(Event.ERROR) == State.SLEEPING


def test_invalid_transition_raises():
    sm = StateMachine(initial_state=State.SLEEPING)
    with pytest.raises(ValueError, match="Invalid transition"):
        sm.send_event(Event.SESSION_READY)


def test_callback_called():
    transitions = []

    def on_transition(old, event, new):
        transitions.append((old, event, new))

    sm = StateMachine(on_transition=on_transition)
    sm.send_event(Event.SETUP_COMPLETE)
    sm.send_event(Event.WAKE_WORD_DETECTED)

    assert len(transitions) == 2
    assert transitions[0] == (State.SETUP, Event.SETUP_COMPLETE, State.SLEEPING)
    assert transitions[1] == (State.SLEEPING, Event.WAKE_WORD_DETECTED, State.WAKING)


def test_time_in_state():
    sm = StateMachine()
    assert sm.time_in_state >= 0
    sm.send_event(Event.SETUP_COMPLETE)
    # Time should reset after transition
    assert sm.time_in_state < 1.0


def test_multiple_cycles():
    """Robot can go through multiple wake/sleep cycles."""
    sm = StateMachine(initial_state=State.SLEEPING)
    for _ in range(3):
        sm.send_event(Event.WAKE_WORD_DETECTED)
        sm.send_event(Event.SESSION_READY)
        sm.send_event(Event.SILENCE_TIMEOUT)
        sm.send_event(Event.COOLDOWN_COMPLETE)
    assert sm.state == State.SLEEPING
