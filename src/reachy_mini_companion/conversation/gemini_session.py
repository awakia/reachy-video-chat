"""Gemini Live API session with bidirectional audio streaming."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from google import genai
from google.genai import types

from reachy_mini_companion.config import AppConfig
from reachy_mini_companion.conversation.system_prompt import (
    load_enabled_tools,
    load_system_prompt,
)

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

ToolCallHandler = Callable[[str, dict[str, Any]], Any]
TranscriptHandler = Callable[[str, str, bool], None]
StatusHandler = Callable[[str], None]


class GeminiSession:
    """Manages a Gemini Live API session with bidirectional audio.

    Handles sending audio/images and receiving audio responses + tool calls.
    """

    def __init__(
        self,
        config: AppConfig,
        tool_declarations: list[types.Tool] | None = None,
        on_tool_call: ToolCallHandler | None = None,
        on_transcript: TranscriptHandler | None = None,
        on_status: StatusHandler | None = None,
    ):
        self.config = config
        self.tool_declarations = tool_declarations
        self.on_tool_call = on_tool_call
        self.on_transcript = on_transcript
        self.on_status = on_status

        self._send_queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
        self._playback_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._session = None
        self._client = None

        # Reconnection state
        self._resumption_handle: str | None = None
        self._go_away_received = False
        self._reconnect_event: asyncio.Event = asyncio.Event()

    def _build_config(self) -> types.LiveConnectConfig:
        """Build the LiveConnectConfig for the Gemini session."""
        system_prompt = load_system_prompt(
            self.config.prompt.default_profile,
            self.config.prompt.profiles_dir,
        )
        enabled_tools = load_enabled_tools(
            self.config.prompt.default_profile,
            self.config.prompt.profiles_dir,
        )

        config_kwargs: dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "input_audio_transcription": types.AudioTranscriptionConfig(),
            "output_audio_transcription": types.AudioTranscriptionConfig(),
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.config.gemini.voice,
                    )
                )
            ),
            "system_instruction": types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
        }

        # Session resumption (preserves context across reconnects)
        resumption_kwargs: dict[str, Any] = {}
        if self._resumption_handle:
            resumption_kwargs["handle"] = self._resumption_handle
        config_kwargs["session_resumption"] = types.SessionResumptionConfig(
            **resumption_kwargs,
        )

        # Context window compression (allows sessions beyond 15min limit)
        config_kwargs["context_window_compression"] = (
            types.ContextWindowCompressionConfig(
                trigger_tokens=1048576,
                sliding_window=types.SlidingWindow(target_tokens=524288),
            )
        )

        if self.tool_declarations:
            # Filter tools by enabled list
            filtered = []
            for tool in self.tool_declarations:
                if hasattr(tool, "function_declarations"):
                    kept = [
                        fd
                        for fd in tool.function_declarations
                        if fd.name in enabled_tools
                    ]
                    if kept:
                        filtered.append(
                            types.Tool(function_declarations=kept)
                        )
            if filtered:
                config_kwargs["tools"] = filtered

        return types.LiveConnectConfig(**config_kwargs)

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Queue PCM16 16kHz mono audio for sending to Gemini."""
        await self._send_queue.put(("audio", audio_bytes))

    async def send_image(self, jpeg_bytes: bytes) -> None:
        """Queue a JPEG image frame for sending to Gemini."""
        await self._send_queue.put(("image", jpeg_bytes))

    async def get_playback_audio(self) -> bytes:
        """Get the next chunk of 24kHz PCM16 output audio."""
        return await self._playback_queue.get()

    def playback_audio_available(self) -> bool:
        """Check if playback audio is available."""
        return not self._playback_queue.empty()

    async def _sender_loop(self, stop_event: asyncio.Event) -> None:
        """Send queued audio/images to Gemini."""
        while not stop_event.is_set() and not self._reconnect_event.is_set():
            try:
                msg = await asyncio.wait_for(self._send_queue.get(), timeout=0.1)
                if self._session:
                    kind, data = msg
                    if kind == "audio":
                        await self._session.send_realtime_input(
                            audio=types.Blob(data=data, mime_type="audio/pcm"),
                        )
                    elif kind == "image":
                        await self._session.send_realtime_input(
                            media=types.Blob(data=data, mime_type="image/jpeg"),
                        )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Sender error: {e}")
                break

    async def _receiver_loop(self, stop_event: asyncio.Event) -> None:
        """Receive responses from Gemini and dispatch audio/tool calls."""
        if not self._session:
            return

        try:
            async for response in self._session.receive():
                if stop_event.is_set():
                    break

                sc = response.server_content

                # Extract audio directly from model_turn parts
                # (avoids SDK warning about non-data parts)
                if sc and sc.model_turn and sc.model_turn.parts:
                    for part in sc.model_turn.parts:
                        if (
                            part.inline_data
                            and isinstance(part.inline_data.data, bytes)
                            and part.inline_data.data
                        ):
                            await self._playback_queue.put(
                                part.inline_data.data
                            )

                # Handle tool calls
                if response.tool_call and response.tool_call.function_calls:
                    await self._handle_tool_calls(response.tool_call.function_calls)

                # Handle transcription
                if self.on_transcript and sc:
                    if sc.input_transcription and sc.input_transcription.text:
                        self.on_transcript(
                            "user",
                            sc.input_transcription.text,
                            bool(sc.input_transcription.finished),
                        )
                    if sc.output_transcription and sc.output_transcription.text:
                        self.on_transcript(
                            "assistant",
                            sc.output_transcription.text,
                            bool(sc.output_transcription.finished),
                        )

                # Handle go_away (server signals upcoming disconnect)
                if response.go_away:
                    logger.warning(
                        f"Gemini go_away received "
                        f"(time_left={response.go_away.time_left})"
                    )
                    self._go_away_received = True

                # Track session resumption handles
                if response.session_resumption_update:
                    update = response.session_resumption_update
                    if update.new_handle and update.resumable:
                        self._resumption_handle = update.new_handle

        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"Receiver error: {e}")
        finally:
            # Signal reconnection if we weren't asked to stop
            if not stop_event.is_set():
                self._reconnect_event.set()

    async def _handle_tool_calls(
        self, function_calls: list[types.FunctionCall]
    ) -> None:
        """Process tool calls and send responses back to Gemini."""
        responses = []
        for fc in function_calls:
            result = ""
            if self.on_tool_call:
                try:
                    result = await self.on_tool_call(fc.name, dict(fc.args) if fc.args else {})
                except Exception as e:
                    logger.error(f"Tool call error ({fc.name}): {e}")
                    result = f"Error: {e}"

            responses.append(
                types.FunctionResponse(
                    name=fc.name,
                    response={"result": str(result)},
                )
            )

        if self._session and responses:
            await self._session.send(
                input=types.LiveClientToolResponse(function_responses=responses)
            )

    @staticmethod
    def _is_permanent_error(e: Exception) -> bool:
        """Check if an error should not be retried."""
        if isinstance(e, (ValueError, TypeError)):
            return True
        error_str = str(e).lower()
        return any(
            kw in error_str
            for kw in [
                "api key",
                "api_key",
                "unauthenticated",
                "permission denied",
                "not supported",
                "403",
                "401",
                "quota",
            ]
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run the full Gemini session lifecycle with auto-reconnection.

        Connects to Gemini, starts sender/receiver loops, and automatically
        reconnects on session timeouts or transient errors. Uses session
        resumption to preserve conversation context across reconnects.
        Stops when stop_event is set or a permanent error occurs.
        """
        model = self.config.gemini.model or MODEL

        self._client = genai.Client(
            api_key=self.config.google_api_key,
            http_options={"api_version": "v1beta"},
        )

        backoff = 1.0
        max_backoff = 30.0
        max_retries = 10

        for attempt in range(max_retries):
            if stop_event.is_set():
                break

            self._go_away_received = False
            self._reconnect_event = asyncio.Event()
            live_config = self._build_config()

            if self._resumption_handle:
                logger.info(
                    f"Reconnecting (attempt {attempt + 1}, resuming session)..."
                )
                if self.on_status:
                    self.on_status("reconnecting")
            else:
                logger.info(
                    f"Connecting to Gemini Live API (model={model})..."
                )
                if self.on_status:
                    self.on_status("connecting")

            try:
                async with self._client.aio.live.connect(
                    model=model, config=live_config
                ) as session:
                    self._session = session
                    logger.info("Gemini session connected")
                    if self.on_status:
                        self.on_status("connected")
                    backoff = 1.0  # Reset on successful connection

                    sender_task = asyncio.create_task(
                        self._sender_loop(stop_event)
                    )
                    receiver_task = asyncio.create_task(
                        self._receiver_loop(stop_event)
                    )

                    # Wait for stop_event or reconnect_event
                    stop_waiter = asyncio.create_task(stop_event.wait())
                    reconnect_waiter = asyncio.create_task(
                        self._reconnect_event.wait()
                    )
                    done, pending = await asyncio.wait(
                        [stop_waiter, reconnect_waiter],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()

                    sender_task.cancel()
                    receiver_task.cancel()
                    await asyncio.gather(
                        sender_task, receiver_task, return_exceptions=True
                    )
                    self._session = None

                # Exited context manager cleanly
                if stop_event.is_set():
                    break

                if self._go_away_received:
                    logger.info("Reconnecting after go_away...")
                    continue  # No backoff for expected go_away

                # Unexpected disconnect
                logger.warning(
                    f"Session ended unexpectedly, "
                    f"retrying in {backoff:.0f}s..."
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

            except Exception as e:
                self._session = None
                if self._is_permanent_error(e):
                    logger.error(f"Permanent error, not retrying: {e}")
                    raise
                logger.warning(
                    f"Connection error: {e}, retrying in {backoff:.0f}s..."
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        logger.info("Gemini session ended")
