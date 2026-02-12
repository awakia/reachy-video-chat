"""Gradio setup wizard for first-time API key configuration."""

from __future__ import annotations

import logging
from typing import Callable

import gradio as gr

logger = logging.getLogger(__name__)


def validate_api_key(key: str) -> tuple[bool, str]:
    """Validate a Google API key by attempting to list models.

    Returns (success, message) tuple.
    """
    if not key or not key.strip():
        return False, "Please enter an API key."

    key = key.strip()
    try:
        from google import genai

        client = genai.Client(api_key=key)
        # Try listing models to verify the key works
        models = list(client.models.list())
        if models:
            return True, f"Valid! Found {len(models)} available models."
        return True, "Valid! API key accepted."
    except Exception as e:
        return False, f"Invalid API key: {e}"


def create_setup_wizard(on_complete: Callable[[str], None]) -> gr.Blocks:
    """Create the Gradio setup wizard UI.

    Args:
        on_complete: Callback with the validated API key when setup finishes.
    """

    with gr.Blocks(title="Reachy Mini Companion - Setup") as wizard:
        gr.Markdown("# Reachy Mini AI Companion - Setup")
        gr.Markdown(
            "Enter your Google Gemini API key to get started. "
            "Get one at [Google AI Studio](https://aistudio.google.com/apikey)."
        )

        api_key_input = gr.Textbox(
            label="Google API Key",
            type="password",
            placeholder="Enter your API key...",
        )
        status_output = gr.Textbox(label="Status", interactive=False)
        save_btn = gr.Button("Validate & Save", variant="primary")

        def handle_save(key: str) -> str:
            success, message = validate_api_key(key)
            if success:
                from reachy_mini_companion.config import save_api_key

                save_api_key(key.strip())
                logger.info("API key saved successfully")
                on_complete(key.strip())
                return f"{message} Key saved. Restarting..."
            return message

        save_btn.click(fn=handle_save, inputs=[api_key_input], outputs=[status_output])

    return wizard
