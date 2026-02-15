"""Main entry point for Reachy Mini AI Companion."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time

from reachy_mini_companion.config import AppConfig, load_config, resolve_db_path, resolve_log_file

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reachy Mini AI Companion")
    parser.add_argument("--config", type=str, help="Path to config YAML override")
    parser.add_argument(
        "--connection-mode", type=str, choices=["auto", "localhost", "network"],
        help="Reachy Mini connection mode",
    )
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
    # Suppress noisy SDK warning about non-data parts in native audio responses
    logging.getLogger("google_genai.types").setLevel(logging.ERROR)


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
        self._sound_player = None
        self._robot = None

        # Dashboard components (simulate mode only)
        self._dashboard_state = None
        self._audio_handler = None
        self._dashboard_stream = None

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
        self._cost_db = CostDatabase(resolve_db_path(self.config.cost.db_path))
        await self._cost_db.initialize()
        self._cost_tracker = CostTracker(self.config, self._cost_db)

        # Robot connection
        robot = None
        if not self.config.reachy.simulate:
            try:
                from reachy_mini import ReachyMini

                mode = self.config.reachy.connection_mode
                robot = ReachyMini(connection_mode=mode)
                robot.__enter__()
                self._robot = robot
                logger.info(f"Connected to Reachy Mini (connection_mode={mode})")
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

        # Sound player
        from reachy_mini_companion.robot.sounds import SoundPlayer

        self._sound_player = SoundPlayer(robot=robot)

        # Wake word detector
        try:
            from reachy_mini_companion.wake import create_wake_detector

            self._wake_detector = create_wake_detector(self.config.wake)
            self._wake_detector.load_model()
            logger.info(f"Wake word backend: {self.config.wake.backend}")
        except ImportError as e:
            logger.warning(f"Wake word detection unavailable: {e}")
            self._wake_detector = None

        # Dashboard for simulate mode
        if self.config.reachy.simulate:
            self._init_dashboard()

        # Transition to SLEEPING
        self._sm.send_event(Event.SETUP_COMPLETE)
        logger.info("Setup complete. Entering SLEEPING state.")

    def _init_dashboard(self) -> None:
        """Initialize dashboard components for simulate mode."""
        try:
            from reachy_mini_companion.web.audio_handler import WebAudioHandler
            from reachy_mini_companion.web.dashboard import DashboardState

            self._dashboard_state = DashboardState()
            self._audio_handler = WebAudioHandler()

            # Track WebRTC audio connection state
            def on_audio_connection(connected: bool):
                self._dashboard_state.audio_connected = connected

            self._audio_handler.set_connection_callback(on_audio_connection)

            # Update dashboard state on state transitions
            original_cb = self._sm._on_transition

            def on_transition(old_state, event, new_state):
                from reachy_mini_companion.state_machine import State

                self._dashboard_state.update_state(new_state.name)
                # Show progress detail for each state
                detail_map = {
                    State.SLEEPING: "",
                    State.WAKING: "Waking up...",
                    State.ACTIVE: "Connecting to Gemini...",
                    State.COOLDOWN: "Session ending...",
                }
                self._dashboard_state.detail = detail_map.get(new_state, "")
                if original_cb:
                    original_cb(old_state, event, new_state)

            self._sm._on_transition = on_transition

            # Wrap tool dispatcher to track expressions/look on dashboard
            original_handle = self._dispatcher.handle

            async def wrapped_handle(name, args):
                result = await original_handle(name, args)
                if name == "robot_expression":
                    self._dashboard_state.update_expression(args.get("action", ""))
                elif name == "robot_look_at":
                    self._dashboard_state.update_look(args.get("direction", ""))
                return result

            self._dispatcher.handle = wrapped_handle

            logger.info("Dashboard components initialized")
        except ImportError as e:
            logger.warning(f"Dashboard unavailable: {e}")
            self._dashboard_state = None
            self._audio_handler = None

    def _launch_dashboard(self) -> None:
        """Launch the Gradio dashboard for simulate mode."""
        from reachy_mini_companion.state_machine import Event, State
        from reachy_mini_companion.web.dashboard import create_dashboard

        def on_wake():
            if self._sm.state == State.SLEEPING:
                self._sm.send_event(Event.WAKE_WORD_DETECTED)
                return "Waking up..."
            return f"Cannot wake from {self._sm.state.name}"

        self._dashboard_stream = create_dashboard(
            self._audio_handler, self._dashboard_state, on_wake
        )
        self._dashboard_stream.launch(
            server_name=self.config.web_ui.host,
            server_port=self.config.web_ui.port,
            share=False,
            prevent_thread_lock=True,
        )
        logger.info(
            f"Dashboard launched at http://{self.config.web_ui.host}:{self.config.web_ui.port}"
        )

    async def run(self) -> None:
        """Run the main application loop."""
        from reachy_mini_companion.state_machine import Event, State

        # Install signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Suppress noisy aioice errors during WebRTC teardown
        _default_handler = loop.get_exception_handler()

        def _quiet_exception_handler(loop, context):
            msg = context.get("message", "")
            if "sendto" in msg or "Transaction" in str(context.get("handle", "")):
                logger.debug("Suppressed aioice teardown error")
                return
            if _default_handler:
                _default_handler(loop, context)
            else:
                loop.default_exception_handler(context)

        loop.set_exception_handler(_quiet_exception_handler)

        # Launch dashboard in simulate mode
        if self._dashboard_state is not None:
            try:
                self._launch_dashboard()
            except Exception as e:
                logger.warning(f"Dashboard unavailable: {e}")

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
                await self._sound_player.play_error()
                try:
                    self._sm.send_event(Event.ERROR)
                except ValueError:
                    pass

        await self.cleanup()

    async def _handle_sleeping(self) -> None:
        """SLEEPING: Monitor mic for wake word."""
        if self._wake_detector is None:
            if self._dashboard_state is None:
                logger.info("No wake word detector. Use Ctrl+C to exit.")
            # Poll quickly so the dashboard Wake button is responsive
            await asyncio.sleep(0.2)
            return

        # In a real deployment, this would read from robot mic
        # For now, sleep briefly to avoid busy-waiting
        await asyncio.sleep(0.1)

        # Wake word detection happens via process_audio() calls
        # which would be driven by the audio capture loop

    async def _handle_waking(self) -> None:
        """WAKING: Check budget, validate API key, wake up robot, connect Gemini."""
        from reachy_mini_companion.state_machine import Event

        # Clear previous errors and transcript on new wake attempt
        if self._dashboard_state is not None:
            self._dashboard_state.clear_error()
            self._dashboard_state.clear_transcript()
            self._dashboard_state.detail = "Validating API key..."

        # Validate API key before attempting connection
        try:
            from google import genai

            client = genai.Client(api_key=self.config.google_api_key)
            await asyncio.to_thread(lambda: next(iter(client.models.list()), None))
            logger.info("Gemini API key validated")
        except Exception as e:
            error_msg = (
                f"Invalid Gemini API key: {e}\n"
                "Check your GOOGLE_API_KEY in .env file. "
                "Get a valid key at https://aistudio.google.com/apikey"
            )
            logger.error(error_msg)
            if self._dashboard_state is not None:
                self._dashboard_state.set_error(error_msg)
            self._sm.send_event(Event.ERROR)
            return

        # Check budget
        if not await self._cost_tracker.check_budget():
            logger.warning("Daily budget exceeded, going back to sleep")
            self._sm.send_event(Event.ERROR)
            return

        # Wake up animation + sound
        await self._controller.wake_up(self.config.robot.wake_up_duration)
        await self._sound_player.play_wake_up()

        # Start cost tracking session
        await self._cost_tracker.start_session()

        self._sm.send_event(Event.SESSION_READY)

    @staticmethod
    def _is_api_key_error(error: Exception) -> bool:
        """Check if an exception is likely caused by an invalid API key."""
        error_str = str(error).lower()
        api_key_indicators = [
            "api key",
            "api_key",
            "invalid key",
            "unauthenticated",
            "permission denied",
            "403",
            "401",
            "authentication",
            "credentials",
        ]
        return any(indicator in error_str for indicator in api_key_indicators)

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

        on_transcript = None
        on_status = None
        if self._dashboard_state is not None:
            on_transcript = self._dashboard_state.append_transcript

            def on_status(status: str):
                detail_map = {
                    "connecting": "Connecting to Gemini...",
                    "connected": "Connected — speak now!",
                    "reconnecting": "Reconnecting...",
                }
                self._dashboard_state.detail = detail_map.get(status, status)

        gemini = GeminiSession(
            config=self.config,
            tool_declarations=self._tool_declarations,
            on_tool_call=self._dispatcher.handle,
            on_transcript=on_transcript,
            on_status=on_status,
        )

        # Attach web audio handler for dashboard mode
        if self._audio_handler is not None:
            self._audio_handler.attach(gemini)

        try:
            async with asyncio.TaskGroup() as tg:
                # Run Gemini session (handles reconnection internally)
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
                # Unwrap TaskGroup ExceptionGroup to get the real error
                root_cause = e
                if hasattr(e, "exceptions"):
                    exceptions = e.exceptions
                    if exceptions:
                        root_cause = exceptions[0]

                error_msg = str(root_cause)
                if self._is_api_key_error(root_cause):
                    error_msg = (
                        f"Gemini API key error: {root_cause}\n"
                        "Please check your GOOGLE_API_KEY in .env file. "
                        "Get a valid key at https://aistudio.google.com/apikey"
                    )
                    logger.error(error_msg)
                else:
                    logger.error(f"Session error: {root_cause}")
                if self._dashboard_state is not None:
                    self._dashboard_state.set_error(error_msg)
        finally:
            if self._audio_handler is not None:
                self._audio_handler.detach()

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

        # Sleep sound + animation
        await self._sound_player.play_sleep()
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
    if args.connection_mode:
        config.reachy.connection_mode = args.connection_mode
    if args.simulate:
        config.reachy.simulate = True

    setup_logging(args.log_level, resolve_log_file(config.logging.file))

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
