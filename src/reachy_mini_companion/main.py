"""Main entry point for Reachy Mini AI Companion."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from reachy_mini_companion.config import load_config

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


def launch_setup_wizard(config):
    """Launch Gradio setup wizard for API key entry."""
    from reachy_mini_companion.web.setup_wizard import create_setup_wizard

    setup_complete = False

    def on_complete(key: str):
        nonlocal setup_complete
        setup_complete = True
        logger.info("Setup complete, please restart the application.")

    wizard = create_setup_wizard(on_complete)
    wizard.launch(
        server_name=config.web_ui.host,
        server_port=config.web_ui.port,
        share=False,
    )


async def run_app(config) -> None:
    """Run the main companion application loop."""
    from reachy_mini_companion.state_machine import Event, State, StateMachine

    sm = StateMachine()

    # Apply CLI overrides
    logger.info(f"Starting Reachy Mini AI Companion (simulate={config.reachy.simulate})")

    # Transition from SETUP to SLEEPING
    sm.send_event(Event.SETUP_COMPLETE)

    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    logger.info("Entering main loop (SLEEPING). Waiting for wake word...")

    # Main loop placeholder - will be completed in commit 8
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    logger.info("Shutting down gracefully")


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
