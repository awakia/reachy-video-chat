"""Main entry point for Reachy Mini AI Companion."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time

from reachy_mini_companion.config import AppConfig, load_config

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reachy Mini AI Companion")
    parser.add_argument("--config", type=str, help="Path to config YAML override")
    parser.add_argument("--host", type=str, help="Reachy Mini host address")
    parser.add_argument("--port", type=int, default=7860, help="Web UI port")
    parser.add_argument("--web", dest="web", action="store_true", default=True)
    parser.add_argument("--no-web", dest="web", action="store_false")
    parser.add_argument("--log-level", type=str, default="INFO")
    parser.add_argument("--dry-run", action="store_true", help="Test config and exit")
    parser.add_argument("--simulate", action="store_true", help="Run without robot hardware")
    return parser.parse_args()


def setup_logging(level: str, log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        from pathlib import Path

        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def launch_setup_wizard(config: AppConfig) -> None:
    """Launch Gradio setup wizard for API key entry."""
    from reachy_mini_companion.web.setup_wizard import create_setup_wizard

    def on_complete(key: str):
        logger.info("Setup complete, please restart the application.")

    wizard = create_setup_wizard(on_complete)
    wizard.launch(
        server_name=config.web_ui.host,
        server_port=config.web_ui.port,
        share=False,
    )


class CompanionApp:
    """Orchestrates the full companion lifecycle."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.shutdown_event = asyncio.Event()

        # Components (initialized in setup)
        self._sm = None
        self._cost_db = None
        self._cost_tracker = None
        self._controller = None
        self._dispatcher = None
        self._tool_declarations = None
        self._wake_detector = None
        self._robot = None

    async def setup(self) -> None:
        """Initialize all components."""
        from reachy_mini_companion.cost.db import CostDatabase
        from reachy_mini_companion.cost.tracker import CostTracker
        from reachy_mini_companion.robot.controller import MovementController
        from reachy_mini_companion.state_machine import Event, StateMachine
        from reachy_mini_companion.tools.core_tools import create_tool_declarations
        from reachy_mini_companion.tools.tool_dispatcher import ToolDispatcher

        # State machine
        self._sm = StateMachine()

        # Cost tracking
        self._cost_db = CostDatabase(self.config.cost.db_path)
        await self._cost_db.initialize()
        self._cost_tracker = CostTracker(self.config, self._cost_db)

        # Robot connection
        robot = None
        if not self.config.reachy.simulate:
            try:
                from reachy_mini import ReachyMini

                robot = ReachyMini(host=self.config.reachy.host)
                robot.__enter__()
                self._robot = robot
                logger.info(f"Connected to Reachy Mini at {self.config.reachy.host}")
            except Exception as e:
                logger.warning(f"Could not connect to robot: {e}. Running in simulate mode.")
        else:
            logger.info("Running in simulate mode (no robot)")

        # Movement controller & tools
        self._controller = MovementController(
            robot=robot,
            expression_speed=self.config.robot.expression_speed,
        )
        self._dispatcher = ToolDispatcher(self._controller)
        self._tool_declarations = create_tool_declarations()

        # Wake word detector
        try:
            from reachy_mini_companion.wake import create_wake_detector

            self._wake_detector = create_wake_detector(self.config.wake)
            self._wake_detector.load_model()
            logger.info(f"Wake word backend: {self.config.wake.backend}")
        except ImportError as e:
            logger.warning(f"Wake word detection unavailable: {e}")
            self._wake_detector = None

        # Transition to SLEEPING
        self._sm.send_event(Event.SETUP_COMPLETE)
        logger.info("Setup complete. Entering SLEEPING state.")

    async def run(self) -> None:
        """Run the main application loop."""
        from reachy_mini_companion.state_machine import Event, State

        # Install signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        logger.info("Starting main loop...")

        while not self.shutdown_event.is_set():
            state = self._sm.state

            try:
                if state == State.SLEEPING:
                    await self._handle_sleeping()

                elif state == State.WAKING:
                    await self._handle_waking()

                elif state == State.ACTIVE:
                    await self._handle_active()

                elif state == State.COOLDOWN:
                    await self._handle_cooldown()

                else:
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in state {state.name}: {e}", exc_info=True)
                try:
                    self._sm.send_event(Event.ERROR)
                except ValueError:
                    pass

        await self.cleanup()

    async def _handle_sleeping(self) -> None:
        """SLEEPING: Monitor mic for wake word."""
        if self._wake_detector is None:
            # No wake word detector - wait for shutdown
            logger.info("No wake word detector. Use Ctrl+C to exit.")
            await asyncio.sleep(1.0)
            return

        # In a real deployment, this would read from robot mic
        # For now, sleep briefly to avoid busy-waiting
        await asyncio.sleep(0.1)

        # Wake word detection happens via process_audio() calls
        # which would be driven by the audio capture loop

    async def _handle_waking(self) -> None:
        """WAKING: Check budget, wake up robot, connect Gemini."""
        from reachy_mini_companion.state_machine import Event

        # Check budget
        if not await self._cost_tracker.check_budget():
            logger.warning("Daily budget exceeded, going back to sleep")
            self._sm.send_event(Event.ERROR)
            return

        # Wake up animation
        await self._controller.wake_up(self.config.robot.wake_up_duration)

        # Start cost tracking session
        await self._cost_tracker.start_session()

        self._sm.send_event(Event.SESSION_READY)

    async def _handle_active(self) -> None:
        """ACTIVE: Run Gemini session with audio I/O."""
        from reachy_mini_companion.conversation.gemini_session import GeminiSession
        from reachy_mini_companion.state_machine import Event
        from reachy_mini_companion.wake.vad import SilenceDetector

        session_stop = asyncio.Event()
        silence_detector = SilenceDetector(
            timeout_sec=self.config.session.silence_timeout_sec,
            rms_threshold=self.config.session.silence_rms_threshold,
        )
        session_start = time.monotonic()

        gemini = GeminiSession(
            config=self.config,
            tool_declarations=self._tool_declarations,
            on_tool_call=self._dispatcher.handle,
        )

        try:
            async with asyncio.TaskGroup() as tg:
                # Run Gemini session
                tg.create_task(gemini.run(session_stop))

                # Run audio bridge if robot is connected
                if self._robot:
                    from reachy_mini_companion.robot.audio import RobotAudioBridge

                    bridge = RobotAudioBridge(self._robot, self.config)
                    tg.create_task(bridge.capture_loop(gemini.send_audio, session_stop))
                    tg.create_task(bridge.playback_loop(gemini.get_playback_audio, session_stop))

                # Monitor for session end conditions
                tg.create_task(
                    self._session_monitor(session_stop, session_start, silence_detector)
                )

        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.error(f"Session error: {e}")

        # End cost tracking
        await self._cost_tracker.end_session()

        # Transition
        if self.shutdown_event.is_set():
            return

        try:
            elapsed = time.monotonic() - session_start
            if elapsed >= self.config.session.max_duration_sec:
                self._sm.send_event(Event.MAX_DURATION)
            else:
                self._sm.send_event(Event.SILENCE_TIMEOUT)
        except ValueError:
            pass

    async def _session_monitor(
        self,
        session_stop: asyncio.Event,
        session_start: float,
        silence_detector,
    ) -> None:
        """Monitor session for timeout/silence conditions."""
        while not session_stop.is_set() and not self.shutdown_event.is_set():
            elapsed = time.monotonic() - session_start

            # Check max duration
            if elapsed >= self.config.session.max_duration_sec:
                logger.info("Max session duration reached")
                session_stop.set()
                return

            await asyncio.sleep(0.5)

        session_stop.set()

    async def _handle_cooldown(self) -> None:
        """COOLDOWN: Disconnect, sleep animation, wait."""
        from reachy_mini_companion.state_machine import Event

        # Sleep animation
        await self._controller.go_to_sleep(self.config.robot.sleep_duration)

        # Wait cooldown period
        await asyncio.sleep(self.config.session.cooldown_sec)

        self._sm.send_event(Event.COOLDOWN_COMPLETE)

    def _handle_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self.shutdown_event.set()

    async def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")

        if self._robot:
            try:
                self._robot.__exit__(None, None, None)
            except Exception:
                pass

        if self._cost_db:
            await self._cost_db.close()

        logger.info("Shutdown complete")


async def run_app(config: AppConfig) -> None:
    """Run the main companion application."""
    app = CompanionApp(config)
    await app.setup()
    await app.run()


def main():
    args = parse_args()
    config = load_config(config_path=args.config)

    # Apply CLI overrides
    if args.host:
        config.reachy.host = args.host
    if args.simulate:
        config.reachy.simulate = True

    setup_logging(args.log_level, config.logging.file)

    if args.dry_run:
        logger.info(f"Config loaded: {config}")
        print("Dry run OK - config valid")
        return

    # Check for API key
    if not config.has_api_key:
        logger.info("No API key found, launching setup wizard...")
        launch_setup_wizard(config)
        return

    logger.info("API key found, starting companion...")
    asyncio.run(run_app(config))


if __name__ == "__main__":
    main()
