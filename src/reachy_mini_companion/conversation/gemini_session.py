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


class GeminiSession:
    """Manages a Gemini Live API session with bidirectional audio.

    Handles sending audio/images and receiving audio responses + tool calls.
    """

    def __init__(
        self,
        config: AppConfig,
        tool_declarations: list[types.Tool] | None = None,
        on_tool_call: ToolCallHandler | None = None,
    ):
        self.config = config
        self.tool_declarations = tool_declarations
        self.on_tool_call = on_tool_call

        self._send_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._playback_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._session = None
        self._client = None

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
        await self._send_queue.put({
            "data": audio_bytes,
            "mime_type": "audio/pcm",
        })

    async def send_image(self, jpeg_bytes: bytes) -> None:
        """Queue a JPEG image frame for sending to Gemini."""
        await self._send_queue.put({
            "data": jpeg_bytes,
            "mime_type": "image/jpeg",
        })

    async def get_playback_audio(self) -> bytes:
        """Get the next chunk of 24kHz PCM16 output audio."""
        return await self._playback_queue.get()

    def playback_audio_available(self) -> bool:
        """Check if playback audio is available."""
        return not self._playback_queue.empty()

    async def _sender_loop(self, stop_event: asyncio.Event) -> None:
        """Send queued audio/images to Gemini."""
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(self._send_queue.get(), timeout=0.1)
                if self._session:
                    await self._session.send(input=msg)
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

                # Handle audio data
                if response.data:
                    await self._playback_queue.put(response.data)

                # Handle tool calls
                if response.tool_call and response.tool_call.function_calls:
                    await self._handle_tool_calls(response.tool_call.function_calls)

        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"Receiver error: {e}")

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

    async def run(self, stop_event: asyncio.Event) -> None:
        """Run the full Gemini session lifecycle.

        Connects to Gemini, starts sender/receiver loops, and runs until
        stop_event is set.
        """
        model = self.config.gemini.model or MODEL
        live_config = self._build_config()

        self._client = genai.Client(
            api_key=self.config.google_api_key,
            http_options={"api_version": "v1beta"},
        )

        logger.info(f"Connecting to Gemini Live API (model={model})...")

        async with self._client.aio.live.connect(
            model=model, config=live_config
        ) as session:
            self._session = session
            logger.info("Gemini session connected")

            sender_task = asyncio.create_task(self._sender_loop(stop_event))
            receiver_task = asyncio.create_task(self._receiver_loop(stop_event))

            try:
                # Wait for stop_event
                await stop_event.wait()
            finally:
                sender_task.cancel()
                receiver_task.cancel()
                try:
                    await asyncio.gather(sender_task, receiver_task, return_exceptions=True)
                except Exception:
                    pass
                self._session = None
                logger.info("Gemini session disconnected")
