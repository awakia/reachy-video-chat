"""Gradio dashboard for development/simulation mode."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import gradio as gr

logger = logging.getLogger(__name__)

_INSTALL_HINT = (
    "fastrtc is required for the web dashboard. "
    "Install with: pip install -e '.[dashboard]'"
)


@dataclass
class DashboardState:
    """Shared state between CompanionApp and dashboard UI."""

    state: str = "SETUP"
    detail: str = ""
    expression: str = ""
    look_direction: str = ""
    last_error: str = ""
    audio_connected: bool = False
    transcript: list = field(default_factory=list)
    user_text_buffer: str = ""
    assistant_text_buffer: str = ""

    def get_status(self) -> tuple[str, str, str, str, str, bool, list]:
        """Return current status for UI polling."""
        return (
            self.state, self.detail, self.expression, self.look_direction,
            self.last_error, self.audio_connected,
            self.get_transcript_for_display(),
        )

    def update_state(self, state_name: str) -> None:
        self.state = state_name

    def update_expression(self, expression: str) -> None:
        self.expression = expression

    def update_look(self, direction: str) -> None:
        self.look_direction = direction

    def set_error(self, message: str) -> None:
        self.last_error = message

    def clear_error(self) -> None:
        self.last_error = ""

    def append_transcript(self, role: str, text: str, finished: bool) -> None:
        """Append transcription text, finalizing when finished."""
        if role == "user":
            self.user_text_buffer += text
            if finished and self.user_text_buffer.strip():
                self.transcript.append(
                    {"role": "user", "content": self.user_text_buffer.strip()}
                )
                self.user_text_buffer = ""
        elif role == "assistant":
            self.assistant_text_buffer += text
            if finished and self.assistant_text_buffer.strip():
                self.transcript.append(
                    {"role": "assistant", "content": self.assistant_text_buffer.strip()}
                )
                self.assistant_text_buffer = ""

    def get_transcript_for_display(self) -> list[dict[str, str]]:
        """Return transcript including any in-progress text."""
        result = list(self.transcript)
        if self.user_text_buffer.strip():
            result.append(
                {"role": "user", "content": self.user_text_buffer.strip() + " ..."}
            )
        if self.assistant_text_buffer.strip():
            result.append(
                {"role": "assistant", "content": self.assistant_text_buffer.strip() + " ..."}
            )
        return result

    def clear_transcript(self) -> None:
        """Clear all transcript data."""
        self.transcript.clear()
        self.user_text_buffer = ""
        self.assistant_text_buffer = ""


def create_dashboard(
    handler: Any,
    dashboard_state: DashboardState,
    on_wake: Callable[[], str | None],
) -> gr.Blocks:
    """Create the Gradio development dashboard with WebRTC audio.

    Uses the WebRTC component directly (no Stream overlay) for a clean
    single-layer layout where nothing overlaps.

    Args:
        handler: WebAudioHandler instance (AsyncStreamHandler).
        dashboard_state: Shared state for UI display.
        on_wake: Callback when Wake Up button is clicked.

    Returns:
        gr.Blocks instance. Call .launch() to start.
    """
    try:
        from fastrtc import WebRTC
    except ImportError:
        raise ImportError(_INSTALL_HINT) from None

    css = (
        ".error-display textarea {"
        "  color: #dc2626 !important;"
        "  border-color: #dc2626 !important;"
        "  font-weight: bold !important;"
        "}"
        ".steps-guide {"
        "  background: #f0f9ff;"
        "  border: 1px solid #bae6fd;"
        "  border-radius: 8px;"
        "  padding: 12px 16px;"
        "}"
    )

    with gr.Blocks(css=css, title="Reachy Mini Companion") as demo:
        gr.Markdown(
            "### How to use\n"
            "1. Click **Record** to connect your microphone\n"
            "2. Click **Wake Up** to start a conversation\n"
            "3. **Talk** to Reachy — you'll hear a voice response",
            elem_classes=["steps-guide"],
        )

        webrtc = WebRTC(
            label="Audio",
            mode="send-receive",
            modality="audio",
            full_screen=False,
        )
        webrtc.stream(fn=handler, inputs=[webrtc], outputs=[webrtc])

        def on_start_recording():
            dashboard_state.audio_connected = True

        def on_stop_recording():
            dashboard_state.audio_connected = False

        webrtc.start_recording(fn=on_start_recording)
        webrtc.stop_recording(fn=on_stop_recording)

        with gr.Row():
            audio_status = gr.Textbox(
                label="Microphone",
                value="Not connected — click Record above",
                interactive=False,
            )
            state_display = gr.Textbox(label="State", interactive=False)

        detail_display = gr.Textbox(
            label="Detail", interactive=False, visible=False,
        )

        error_display = gr.Textbox(
            label="Error",
            interactive=False,
            visible=False,
            elem_classes=["error-display"],
        )

        with gr.Row():
            expression_display = gr.Textbox(
                label="Expression", interactive=False,
            )
            look_display = gr.Textbox(
                label="Look Direction", interactive=False,
            )

        wake_btn = gr.Button("Wake Up", variant="primary", size="lg")
        wake_status = gr.Textbox(label="", interactive=False, visible=False)

        chatbot = gr.Chatbot(
            label="Conversation",
            type="messages",
            height=300,
        )

        def poll_status():
            state, detail, expression, look, error, connected, transcript = (
                dashboard_state.get_status()
            )
            can_wake = state == "SLEEPING"
            mic_text = "Connected" if connected else "Not connected — click Record above"
            return (
                state,
                gr.update(value=detail, visible=bool(detail)),
                expression,
                look,
                gr.update(value=error, visible=bool(error)),
                gr.update(
                    interactive=can_wake,
                    variant="primary" if can_wake else "secondary",
                ),
                mic_text,
                transcript,
            )

        timer = gr.Timer(0.5)
        timer.tick(
            fn=poll_status,
            outputs=[
                state_display, detail_display, expression_display,
                look_display, error_display, wake_btn, audio_status,
                chatbot,
            ],
        )
        wake_btn.click(fn=on_wake, outputs=[wake_status])

    return demo
