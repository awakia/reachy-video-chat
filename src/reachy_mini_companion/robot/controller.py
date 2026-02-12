"""Movement controller for Reachy Mini robot."""

from __future__ import annotations

import asyncio
import logging

from reachy_mini_companion.robot.expressions import EXPRESSIONS, LOOK_DIRECTIONS

logger = logging.getLogger(__name__)


class MovementController:
    """Controls Reachy Mini head, antennas, and body movements.

    All SDK calls are wrapped in asyncio.to_thread() since they are blocking.
    """

    def __init__(self, robot=None, expression_speed: float = 1.0):
        self.robot = robot
        self.expression_speed = expression_speed

    async def express(self, action: str, intensity: float = 1.0) -> str:
        """Execute an expression choreography.

        Args:
            action: Expression name (e.g., "nod", "shake_head").
            intensity: Scale factor for movements (0.0-2.0).

        Returns:
            Result message.
        """
        if action not in EXPRESSIONS:
            available = ", ".join(EXPRESSIONS.keys())
            return f"Unknown expression '{action}'. Available: {available}"

        steps = EXPRESSIONS[action]
        logger.info(f"Expressing: {action} (intensity={intensity})")

        if self.robot is None:
            logger.info(f"[Simulate] expression: {action}")
            return f"Performed {action}"

        for step in steps:
            head_kwargs = {}
            for key, value in step.get("head_pose", {}).items():
                head_kwargs[key] = value * intensity

            duration = step["duration"] / self.expression_speed
            antennas = step.get("antennas", [0, 0])
            body_yaw = step.get("body_yaw", 0) * intensity

            await self._goto(
                head_kwargs=head_kwargs,
                antennas=[a * intensity for a in antennas],
                body_yaw=body_yaw,
                duration=duration,
            )

        return f"Performed {action}"

    async def move_head(self, direction: str) -> str:
        """Move head to look in a direction.

        Args:
            direction: One of "left", "right", "up", "down", "center", "user".

        Returns:
            Result message.
        """
        if direction not in LOOK_DIRECTIONS:
            available = ", ".join(LOOK_DIRECTIONS.keys())
            return f"Unknown direction '{direction}'. Available: {available}"

        head_kwargs = LOOK_DIRECTIONS[direction]
        logger.info(f"Looking: {direction}")

        if self.robot is None:
            logger.info(f"[Simulate] look_at: {direction}")
            return f"Looking {direction}"

        await self._goto(head_kwargs=head_kwargs, duration=0.5)
        return f"Looking {direction}"

    async def wake_up(self, duration: float = 1.0) -> None:
        """Wake up animation: head lifts, antennas perk up."""
        logger.info("Wake up animation")
        if self.robot is None:
            logger.info("[Simulate] wake_up")
            return

        # Start from sleep position -> neutral
        await self._goto(
            head_kwargs={"pitch": -10},
            antennas=[-20, -20],
            duration=duration,
        )
        await self._goto(
            head_kwargs={"pitch": 0},
            antennas=[0, 0],
            duration=duration * 0.5,
        )

    async def go_to_sleep(self, duration: float = 1.5) -> None:
        """Sleep animation: head droops, antennas droop."""
        logger.info("Sleep animation")
        if self.robot is None:
            logger.info("[Simulate] go_to_sleep")
            return

        await self._goto(
            head_kwargs={"pitch": 25},
            antennas=[25, 25],
            duration=duration,
        )

    async def _goto(
        self,
        head_kwargs: dict | None = None,
        antennas: list[float] | None = None,
        body_yaw: float = 0,
        duration: float = 0.5,
    ) -> None:
        """Low-level movement via SDK, run in thread."""
        if self.robot is None:
            return

        try:
            from reachy_mini import create_head_pose

            head_pose = create_head_pose(**(head_kwargs or {}), degrees=True)
            ant = antennas or [0, 0]

            await asyncio.to_thread(
                self.robot.goto_target,
                head=head_pose,
                antennas=ant,
                body_yaw=body_yaw,
                duration=duration,
            )
        except Exception as e:
            logger.error(f"Movement error: {e}")
