"""Tests for tool declarations, dispatcher, and controller."""

import pytest

from reachy_mini_companion.robot.controller import MovementController
from reachy_mini_companion.robot.expressions import EXPRESSIONS, LOOK_DIRECTIONS
from reachy_mini_companion.tools.core_tools import create_tool_declarations
from reachy_mini_companion.tools.tool_dispatcher import ToolDispatcher


def test_create_tool_declarations():
    """Should create valid tool declarations."""
    tools = create_tool_declarations()
    assert len(tools) == 1
    tool = tools[0]
    names = [fd.name for fd in tool.function_declarations]
    assert "robot_expression" in names
    assert "robot_look_at" in names


def test_expression_actions_in_declaration():
    """All expression actions should be listed in the tool enum."""
    tools = create_tool_declarations()
    expr_decl = next(
        fd for fd in tools[0].function_declarations if fd.name == "robot_expression"
    )
    action_enum = expr_decl.parameters.properties["action"].enum
    for action in EXPRESSIONS:
        assert action in action_enum


def test_look_directions_in_declaration():
    """All look directions should be listed in the tool enum."""
    tools = create_tool_declarations()
    look_decl = next(
        fd for fd in tools[0].function_declarations if fd.name == "robot_look_at"
    )
    direction_enum = look_decl.parameters.properties["direction"].enum
    for direction in LOOK_DIRECTIONS:
        assert direction in direction_enum


class TestMovementController:
    @pytest.fixture
    def controller(self):
        """Controller in simulate mode (no robot)."""
        return MovementController(robot=None)

    async def test_express_nod(self, controller):
        result = await controller.express("nod")
        assert "nod" in result.lower()

    async def test_express_all(self, controller):
        """All expressions should work in simulate mode."""
        for action in EXPRESSIONS:
            result = await controller.express(action)
            assert action in result.lower()

    async def test_express_unknown(self, controller):
        result = await controller.express("nonexistent")
        assert "unknown" in result.lower() or "Unknown" in result

    async def test_express_with_intensity(self, controller):
        result = await controller.express("nod", intensity=1.5)
        assert "nod" in result.lower()

    async def test_move_head_all_directions(self, controller):
        for direction in LOOK_DIRECTIONS:
            result = await controller.move_head(direction)
            assert direction in result.lower()

    async def test_move_head_unknown(self, controller):
        result = await controller.move_head("nowhere")
        assert "unknown" in result.lower() or "Unknown" in result

    async def test_wake_up(self, controller):
        await controller.wake_up()  # Should not raise

    async def test_go_to_sleep(self, controller):
        await controller.go_to_sleep()  # Should not raise


class TestToolDispatcher:
    @pytest.fixture
    def dispatcher(self):
        controller = MovementController(robot=None)
        return ToolDispatcher(controller)

    async def test_dispatch_expression(self, dispatcher):
        result = await dispatcher.handle("robot_expression", {"action": "nod"})
        assert "nod" in result.lower()

    async def test_dispatch_expression_with_intensity(self, dispatcher):
        result = await dispatcher.handle(
            "robot_expression", {"action": "surprise", "intensity": 1.5}
        )
        assert "surprise" in result.lower()

    async def test_dispatch_look_at(self, dispatcher):
        result = await dispatcher.handle("robot_look_at", {"direction": "left"})
        assert "left" in result.lower()

    async def test_dispatch_unknown_tool(self, dispatcher):
        result = await dispatcher.handle("unknown_tool", {})
        assert "unknown" in result.lower() or "Unknown" in result
