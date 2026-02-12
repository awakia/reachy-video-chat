"""Routes tool calls from Gemini to the appropriate controller methods."""

from __future__ import annotations

import logging
from typing import Any

from reachy_mini_companion.robot.controller import MovementController

logger = logging.getLogger(__name__)


class ToolDispatcher:
    """Dispatches tool calls to MovementController methods."""

    def __init__(self, controller: MovementController):
        self.controller = controller

    async def handle(self, name: str, args: dict[str, Any]) -> str:
        """Handle a tool call by name.

        Args:
            name: Tool function name.
            args: Tool function arguments.

        Returns:
            Result string to send back to Gemini.
        """
        logger.info(f"Tool call: {name}({args})")

        if name == "robot_expression":
            action = args.get("action", "")
            intensity = float(args.get("intensity", 1.0))
            return await self.controller.express(action, intensity)

        elif name == "robot_look_at":
            direction = args.get("direction", "center")
            return await self.controller.move_head(direction)

        else:
            logger.warning(f"Unknown tool: {name}")
            return f"Unknown tool: {name}"
