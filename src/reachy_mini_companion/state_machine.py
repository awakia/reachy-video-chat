"""State machine for the companion app lifecycle."""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable

logger = logging.getLogger(__name__)


class State(Enum):
    SETUP = auto()
    SLEEPING = auto()
    WAKING = auto()
    ACTIVE = auto()
    COOLDOWN = auto()


class Event(Enum):
    SETUP_COMPLETE = auto()
    WAKE_WORD_DETECTED = auto()
    SESSION_READY = auto()
    SILENCE_TIMEOUT = auto()
    MAX_DURATION = auto()
    COOLDOWN_COMPLETE = auto()
    ERROR = auto()


# Valid transitions: (current_state, event) -> next_state
TRANSITIONS: dict[tuple[State, Event], State] = {
    (State.SETUP, Event.SETUP_COMPLETE): State.SLEEPING,
    (State.SLEEPING, Event.WAKE_WORD_DETECTED): State.WAKING,
    (State.WAKING, Event.SESSION_READY): State.ACTIVE,
    (State.WAKING, Event.ERROR): State.SLEEPING,
    (State.ACTIVE, Event.SILENCE_TIMEOUT): State.COOLDOWN,
    (State.ACTIVE, Event.MAX_DURATION): State.COOLDOWN,
    (State.ACTIVE, Event.ERROR): State.COOLDOWN,
    (State.COOLDOWN, Event.COOLDOWN_COMPLETE): State.SLEEPING,
    (State.COOLDOWN, Event.ERROR): State.SLEEPING,
}

TransitionCallback = Callable[[State, Event, State], None]


class StateMachine:
    """Simple state machine with transition callbacks."""

    def __init__(
        self,
        initial_state: State = State.SETUP,
        on_transition: TransitionCallback | None = None,
    ):
        self._state = initial_state
        self._entered_at = time.monotonic()
        self._on_transition = on_transition

    @property
    def state(self) -> State:
        return self._state

    @property
    def time_in_state(self) -> float:
        """Seconds spent in current state."""
        return time.monotonic() - self._entered_at

    def send_event(self, event: Event) -> State:
        """Process an event and transition if valid.

        Returns the new state (or current state if transition is invalid).
        Raises ValueError for invalid transitions.
        """
        key = (self._state, event)
        if key not in TRANSITIONS:
            raise ValueError(
                f"Invalid transition: {self._state.name} + {event.name}"
            )

        old_state = self._state
        new_state = TRANSITIONS[key]
        self._state = new_state
        self._entered_at = time.monotonic()

        logger.info(f"State: {old_state.name} -> {new_state.name} (event={event.name})")

        if self._on_transition:
            self._on_transition(old_state, event, new_state)

        return new_state
