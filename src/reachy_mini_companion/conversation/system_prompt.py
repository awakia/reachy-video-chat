"""System prompt and tool list loading from profile files."""

from __future__ import annotations

import logging

from reachy_mini_companion.config import resolve_profiles_dir

logger = logging.getLogger(__name__)


def load_system_prompt(profile: str, profiles_dir: str = "") -> str:
    """Load system prompt from profiles/<name>/instructions.txt.

    Args:
        profile: Profile name (e.g., "default", "kids").
        profiles_dir: Directory containing profile folders (empty = bundled).

    Returns:
        The system prompt text, or a fallback default.
    """
    path = resolve_profiles_dir(profiles_dir) / profile / "instructions.txt"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        logger.info(f"Loaded system prompt from {path} ({len(text)} chars)")
        return text

    logger.warning(f"Profile '{profile}' instructions.txt not found at {path}")
    return "You are Reachy Mini, a friendly robot companion. Be helpful and concise."


def load_enabled_tools(profile: str, profiles_dir: str = "") -> list[str]:
    """Load enabled tool names from profiles/<name>/tools.txt.

    Args:
        profile: Profile name.
        profiles_dir: Directory containing profile folders (empty = bundled).

    Returns:
        List of enabled tool names.
    """
    path = resolve_profiles_dir(profiles_dir) / profile / "tools.txt"
    if path.exists():
        tools = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        logger.info(f"Loaded {len(tools)} enabled tools from {path}")
        return tools

    logger.warning(f"Profile '{profile}' tools.txt not found at {path}")
    return ["robot_expression", "robot_look_at"]
