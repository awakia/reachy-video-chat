"""Tool declarations for Gemini function calling."""

from __future__ import annotations

from google.genai import types

from reachy_mini_companion.robot.expressions import EXPRESSIONS, LOOK_DIRECTIONS


def create_tool_declarations() -> list[types.Tool]:
    """Create tool declarations for robot control.

    Returns:
        List of Tool objects for Gemini function calling.
    """
    expression_actions = list(EXPRESSIONS.keys())
    look_directions = list(LOOK_DIRECTIONS.keys())

    declarations = [
        types.FunctionDeclaration(
            name="robot_expression",
            description=(
                "Make the robot perform a physical expression or gesture. "
                "Use this to show emotions during conversation."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "action": types.Schema(
                        type="STRING",
                        description=f"The expression to perform. One of: {', '.join(expression_actions)}",
                        enum=expression_actions,
                    ),
                    "intensity": types.Schema(
                        type="NUMBER",
                        description="Movement intensity from 0.5 (subtle) to 2.0 (exaggerated). Default 1.0.",
                    ),
                },
                required=["action"],
            ),
        ),
        types.FunctionDeclaration(
            name="robot_look_at",
            description=(
                "Move the robot's head to look in a direction. "
                "Use this to direct attention or respond to spatial cues."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "direction": types.Schema(
                        type="STRING",
                        description=f"Direction to look. One of: {', '.join(look_directions)}",
                        enum=look_directions,
                    ),
                },
                required=["direction"],
            ),
        ),
    ]

    return [types.Tool(function_declarations=declarations)]
